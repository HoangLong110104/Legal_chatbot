"""
Công cụ Benchmark & Đánh giá hiệu năng 3 Engine: Ollama vs. vLLM vs. SGLang
Đo lường 3 nhóm tiêu chí chính:
1. Độ tốn Token (Input Tokens, Output Tokens, Cached Tokens, Total Tokens)
2. Tốc độ phản hồi (TTFT - ms, Throughput - tokens/s, E2E Latency - s)
3. Độ tiêu hao tài nguyên (VRAM Idle/Peak MB, GPU Util %, GPU Power W, System RAM MB, CPU %)

Cách chạy:
  - Đo Ollama trên máy hiện tại:
      python benchmark_eval.py --engine ollama --model qwen2.5:3b
  - Đo vLLM (trên Linux hoặc qua IP):
      python benchmark_eval.py --engine vllm --url http://127.0.0.1:8001/v1 --model Qwen/Qwen2.5-3B-Instruct
  - Đo SGLang (trên Linux hoặc qua IP):
      python benchmark_eval.py --engine sglang --url http://127.0.0.1:30000/v1 --model Qwen/Qwen2.5-3B-Instruct
  - Tổng hợp bảng so sánh từ các file kết quả đã đo:
      python benchmark_eval.py --compare
"""

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx

try:
    import psutil
except ImportError:
    psutil = None

RESULT_DIR = Path(__file__).resolve().parent / "result"
if RESULT_DIR.exists() and RESULT_DIR.is_file():
    if RESULT_DIR.stat().st_size == 0:
        RESULT_DIR.unlink()
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# =====================================================================
# BỘ DỮ LIỆU CÂU HỎI & NGỮ CẢNH PHÁP LÝ CHUẨN ĐỂ BENCHMARK
# (Đảm bảo cả 3 Engine nhận đúng 100% cùng một lượng Context & Câu hỏi)
# =====================================================================

SYSTEM_PROMPT = (
    "Bạn là Chuyên gia / Trợ lý Pháp luật Việt Nam cao cấp. Nhiệm vụ của bạn là tư vấn và giải đáp "
    "chính xác, khách quan cho người dân dựa trên các điều luật trong CONTEXT được cung cấp.\n"
    "QUY TẮC BẮT BUỘC:\n"
    "1. Trực tiếp giải đáp câu hỏi của người dùng ở ngay câu đầu tiên.\n"
    "2. Đối chiếu và phân tích cụ thể tình huống thực tế của người hỏi với các điều kiện trong luật.\n"
    "3. Trích dẫn chính xác: Điểm mấy, Khoản mấy, Điều mấy, Văn bản nào."
)

SHARED_MARRIAGE_CONTEXT = """=== [52_2014_QH13 | Điều 8: Điều kiện kết hôn] (Hiệu lực: 2015-01-01) ===
Điều 8. Điều kiện kết hôn
1. Nam, nữ kết hôn với nhau phải tuân theo các điều kiện sau đây:
a) Nam từ đủ 20 tuổi trở lên, nữ từ đủ 18 tuổi trở lên;
b) Việc kết hôn do nam và nữ tự nguyện quyết định;
c) Không bị mất năng lực hành vi dân sự;
d) Việc kết hôn không thuộc một trong các trường hợp cấm kết hôn theo quy định tại các Điểm a, b, c và d khoản 2 Điều 5 của Luật này.
2. Nhà nước không thừa nhận hôn nhân giữa những người cùng giới tính.

=== [52_2014_QH13 | Điều 5: Bảo vệ chế độ hôn nhân và gia đình] (Hiệu lực: 2015-01-01) ===
Điều 5. Bảo vệ chế độ hôn nhân và gia đình
1. Quan hệ hôn nhân và gia đình được xác lập, thực hiện theo quy định của Luật này được tôn trọng và được pháp luật bảo vệ.
2. Cấm các hành vi sau đây:
a) Kết hôn giả tạo, ly hôn giả tạo;
b) Tảo hôn, cưỡng ép kết hôn, lừa dối kết hôn, cản trở kết hôn;
c) Người đang có vợ, có chồng mà kết hôn hoặc chung sống như vợ chồng với người khác;
d) Kết hôn hoặc chung sống như vợ chồng giữa những người cùng dòng máu về trực hệ; giữa những người có họ trong phạm vi ba đời.

=== [52_2014_QH13 | Điều 9: Đăng ký kết hôn] (Hiệu lực: 2015-01-01) ===
Điều 9. Đăng ký kết hôn
1. Việc kết hôn phải được đăng ký và do cơ quan nhà nước có thẩm quyền thực hiện theo quy định của Luật này và pháp luật về hộ tịch. Việc kết hôn không được đăng ký theo quy định tại khoản này thì không có giá trị pháp lý.
"""

SHARED_TRAFFIC_CONTEXT = """=== [168_2024_ND_CP | Điều 6: Xử phạt người điều khiển xe ô tô vi phạm quy tắc giao thông đường bộ] (Hiệu lực: 2025-01-01) ===
Điều 6. Xử phạt, trừ điểm giấy phép lái xe của người điều khiển xe ô tô
1. Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng đối với người điều khiển xe thực hiện hành vi không chấp hành hiệu lệnh của đèn tín hiệu giao thông (vượt đèn đỏ, đèn vàng).
2. Phạt tiền từ 30.000.000 đồng đến 40.000.000 đồng đối với người điều khiển xe trên đường mà trong máu hoặc hơi thở có nồng độ cồn vượt quá 80 miligam/100 mililít máu hoặc vượt quá 0,4 miligam/1 lít khí thở.
3. Hình thức xử phạt bổ sung và trừ điểm GPLX: Trừ 04 điểm giấy phép lái xe đối với hành vi vượt đèn đỏ; Tước quyền sử dụng GPLX từ 22 tháng đến 24 tháng đối với vi phạm nồng độ cồn mức kịch khung.

=== [45_2019_QH14 | Điều 107: Làm thêm giờ] (Hiệu lực: 2021-01-01) ===
Điều 107. Làm thêm giờ
1. Thời gian làm thêm giờ là khoảng thời gian làm việc ngoài thời giờ làm việc bình thường theo quy định của pháp luật, thỏa ước lao động tập thể hoặc nội quy lao động.
2. Người sử dụng lao động được sử dụng người lao động làm thêm giờ khi đáp ứng đầy đủ các yêu cầu: Phải được sự đồng ý của người lao động; Bảo đảm số giờ làm thêm của người lao động không quá 50% số giờ làm việc bình thường trong 01 ngày; không quá 40 giờ trong 01 tháng và không quá 200 giờ trong 01 năm (trừ một số ngành nghề đặc biệt không quá 300 giờ trong 01 năm).
"""

BENCHMARK_TEST_CASES = [
    {
        "id": "Q1_Marriage_Age",
        "category": "Hôn nhân & Gia đình",
        "query": "Tôi năm nay 25 tuổi cưới vợ 17 tuổi có được đăng kí kết hôn không?",
        "context": SHARED_MARRIAGE_CONTEXT
    },
    {
        "id": "Q2_Marriage_SameContext_CacheTest",
        "category": "Hôn nhân & Gia đình (Test Prefix Cache)",
        "query": "Hai người cùng giới tính hoặc có họ trong phạm vi ba đời có được phép đăng ký kết hôn với nhau không?",
        "context": SHARED_MARRIAGE_CONTEXT
    },
    {
        "id": "Q3_Marriage_Unregistered_CacheTest",
        "category": "Hôn nhân & Gia đình (Test Prefix Cache)",
        "query": "Tổ chức đám cưới nhưng không đi đăng ký kết hôn tại cơ quan nhà nước thì có giá trị pháp lý không?",
        "context": SHARED_MARRIAGE_CONTEXT
    },
    {
        "id": "Q4_Traffic_RedLight",
        "category": "Giao thông đường bộ",
        "query": "Xe ô tô vượt đèn đỏ theo Nghị định 168/2024 bị phạt bao nhiêu tiền và trừ mấy điểm bằng lái?",
        "context": SHARED_TRAFFIC_CONTEXT
    },
    {
        "id": "Q5_Labor_Overtime_CacheTest",
        "category": "Lao động (Test Prefix Cache)",
        "query": "Công ty bắt nhân viên làm thêm 60 giờ trong 1 tháng có đúng quy định Bộ luật Lao động không?",
        "context": SHARED_TRAFFIC_CONTEXT
    }
]


# =====================================================================
# BỘ GIÁM SÁT TÀI NGUYÊN PHẦN CỨNG (GPU VRAM, GPU %, WATT, CPU, RAM)
# =====================================================================

class HardwareMonitor:
    def __init__(self, interval: float = 0.2):
        self.interval = interval
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.vram_samples: List[float] = []
        self.gpu_util_samples: List[float] = []
        self.gpu_power_samples: List[float] = []
        self.cpu_samples: List[float] = []
        self.ram_samples: List[float] = []

    @staticmethod
    def query_gpu_snapshot() -> Dict[str, float]:
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,memory.total,utilization.gpu,power.draw",
                    "--format=csv,noheader,nounits"
                ],
                stderr=subprocess.DEVNULL,
                text=True
            ).strip()
            first_line = out.splitlines()[0]
            parts = [p.strip() for p in first_line.split(",")]
            return {
                "vram_used_mb": float(parts[0]) if parts[0] != "[N/A]" else 0.0,
                "vram_total_mb": float(parts[1]) if parts[1] != "[N/A]" else 0.0,
                "gpu_util_pct": float(parts[2]) if parts[2] != "[N/A]" else 0.0,
                "gpu_power_w": float(parts[3]) if parts[3] != "[N/A]" else 0.0,
            }
        except Exception:
            return {"vram_used_mb": 0.0, "vram_total_mb": 0.0, "gpu_util_pct": 0.0, "gpu_power_w": 0.0}

    def _loop(self):
        while self.running:
            snap = self.query_gpu_snapshot()
            if snap["vram_used_mb"] > 0:
                self.vram_samples.append(snap["vram_used_mb"])
                self.gpu_util_samples.append(snap["gpu_util_pct"])
                self.gpu_power_samples.append(snap["gpu_power_w"])
            if psutil:
                self.cpu_samples.append(psutil.cpu_percent(interval=None))
                self.ram_samples.append(psutil.virtual_memory().used / (1024 * 1024))
            time.sleep(self.interval)

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self) -> Dict[str, float]:
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        return {
            "vram_peak_mb": round(max(self.vram_samples), 1) if self.vram_samples else 0.0,
            "vram_avg_mb": round(statistics.mean(self.vram_samples), 1) if self.vram_samples else 0.0,
            "gpu_util_avg_pct": round(statistics.mean(self.gpu_util_samples), 1) if self.gpu_util_samples else 0.0,
            "gpu_util_peak_pct": round(max(self.gpu_util_samples), 1) if self.gpu_util_samples else 0.0,
            "gpu_power_avg_w": round(statistics.mean(self.gpu_power_samples), 1) if self.gpu_power_samples else 0.0,
            "cpu_avg_pct": round(statistics.mean(self.cpu_samples), 1) if self.cpu_samples else 0.0,
            "cpu_peak_pct": round(max(self.cpu_samples), 1) if self.cpu_samples else 0.0,
            "ram_avg_mb": round(statistics.mean(self.ram_samples), 1) if self.ram_samples else 0.0,
            "ram_peak_mb": round(max(self.ram_samples), 1) if self.ram_samples else 0.0,
        }


# =====================================================================
# HÀM ĐO LƯỜNG CHO OLLAMA & OPENAI-COMPATIBLE (vLLM / SGLang)
# =====================================================================

def build_user_prompt(query: str, context: str) -> str:
    return (
        f"CĂN CỨ PHÁP LÝ (CONTEXT):\n{context}\n\n"
        f"CÂU HỎI CỦA NGƯỜI DÂN:\n\"{query}\"\n\n"
        f"YÊU CẦU TRẢ LỜI:\n"
        f"1. Trực tiếp kết luận ngay ở đầu: Trường hợp này CÓ ĐƯỢC hay KHÔNG ĐƯỢC (hoặc nêu cụ thể mức phạt)?\n"
        f"2. Phân tích cụ thể các điều kiện theo luật và đối chiếu với tình huống của người hỏi.\n"
        f"3. Trích dẫn chính xác Điểm, Khoản, Điều và số hiệu văn bản."
    )


async def run_ollama_query(client: httpx.AsyncClient, base_url: str, model: str, user_prompt: str) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "stream": True,
        "options": {"temperature": 0.1, "num_predict": 800}
    }

    start_t = time.perf_counter()
    first_token_t = None
    answer_chunks = []
    prompt_tokens = 0
    completion_tokens = 0

    async with client.stream("POST", url, json=payload, timeout=120.0) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.strip():
                continue
            data = json.loads(line)
            content_piece = data.get("message", {}).get("content", "")
            if content_piece:
                if first_token_t is None:
                    first_token_t = time.perf_counter()
                answer_chunks.append(content_piece)
            if data.get("done"):
                prompt_tokens = data.get("prompt_eval_count", 0)
                completion_tokens = data.get("eval_count", len(answer_chunks))

    end_t = time.perf_counter()
    ttft_ms = ((first_token_t - start_t) * 1000) if first_token_t else ((end_t - start_t) * 1000)
    e2e_s = end_t - start_t
    gen_duration_s = (end_t - first_token_t) if (first_token_t and end_t > first_token_t) else e2e_s
    tps = completion_tokens / gen_duration_s if gen_duration_s > 0 else 0.0

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": 0,
        "total_tokens": prompt_tokens + completion_tokens,
        "ttft_ms": round(ttft_ms, 1),
        "tps": round(tps, 2),
        "e2e_s": round(e2e_s, 2),
        "answer_preview": "".join(answer_chunks)[:160].replace("\n", " ") + "..."
    }


async def run_openai_compat_query(client: httpx.AsyncClient, base_url: str, model: str, user_prompt: str) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": 0.1,
        "max_tokens": 800
    }

    start_t = time.perf_counter()
    first_token_t = None
    answer_chunks = []
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0

    async with client.stream("POST", url, json=payload, timeout=120.0) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            raw = line[6:].strip()
            if not raw or raw == "[DONE]":
                continue
            data = json.loads(raw)
            choices = data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {}).get("content", "")
                if delta:
                    if first_token_t is None:
                        first_token_t = time.perf_counter()
                    answer_chunks.append(delta)
            usage = data.get("usage")
            if usage:
                prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                completion_tokens = usage.get("completion_tokens", completion_tokens)
                details = usage.get("prompt_tokens_details") or {}
                cached_tokens = details.get("cached_tokens", usage.get("cached_tokens", 0))

    end_t = time.perf_counter()
    if completion_tokens == 0:
        completion_tokens = len(answer_chunks)
    if prompt_tokens == 0:
        # Ước lượng fallback nếu server không bật stream_options.include_usage
        prompt_tokens = int(len(SYSTEM_PROMPT + user_prompt) / 3.2)

    ttft_ms = ((first_token_t - start_t) * 1000) if first_token_t else ((end_t - start_t) * 1000)
    e2e_s = end_t - start_t
    gen_duration_s = (end_t - first_token_t) if (first_token_t and end_t > first_token_t) else e2e_s
    tps = completion_tokens / gen_duration_s if gen_duration_s > 0 else 0.0

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "ttft_ms": round(ttft_ms, 1),
        "tps": round(tps, 2),
        "e2e_s": round(e2e_s, 2),
        "answer_preview": "".join(answer_chunks)[:160].replace("\n", " ") + "..."
    }


async def evaluate_engine(engine: str, base_url: str, model: str) -> Dict[str, Any]:
    print("=" * 72)
    print(f"🚀 BẮT ĐẦU ĐÁNH GIÁ ENGINE: {engine.upper()} | Model: {model}")
    print(f"📍 Endpoint: {base_url}")
    print("=" * 72)

    idle_gpu = HardwareMonitor.query_gpu_snapshot()
    print(f"📊 Trạng thái GPU trước khi chạy (Idle): VRAM = {idle_gpu['vram_used_mb']} / {idle_gpu['vram_total_mb']} MB")

    monitor = HardwareMonitor(interval=0.2)
    monitor.start()

    results = []
    async with httpx.AsyncClient() as client:
        # Warm-up 1 request ngắn để nạp model vào VRAM
        print("🔥 Đang chạy Warm-up request để đảm bảo model đã nạp vào GPU...")
        warmup_prompt = build_user_prompt("Xin chào", SHARED_MARRIAGE_CONTEXT[:300])
        try:
            if engine == "ollama":
                await run_ollama_query(client, base_url, model, warmup_prompt)
            else:
                await run_openai_compat_query(client, base_url, model, warmup_prompt)
        except Exception as e:
            monitor.stop()
            print(f"❌ Lỗi kết nối tới {engine.upper()} tại {base_url}: {e}")
            raise

        loaded_gpu = HardwareMonitor.query_gpu_snapshot()
        print(f"✅ Warm-up hoàn tất. VRAM sau khi nạp model: {loaded_gpu['vram_used_mb']} MB\n")

        for idx, tc in enumerate(BENCHMARK_TEST_CASES, 1):
            print(f"▶ [{idx}/{len(BENCHMARK_TEST_CASES)}] Đang đo {tc['id']} ({tc['category']})...")
            u_prompt = build_user_prompt(tc["query"], tc["context"])
            if engine == "ollama":
                res = await run_ollama_query(client, base_url, model, u_prompt)
            else:
                res = await run_openai_compat_query(client, base_url, model, u_prompt)

            res["test_id"] = tc["id"]
            res["category"] = tc["category"]
            results.append(res)
            print(
                f"   ✓ TTFT: {res['ttft_ms']} ms | TPS: {res['tps']} tok/s | E2E: {res['e2e_s']}s | "
                f"Tokens (In/Out/Cached): {res['prompt_tokens']}/{res['completion_tokens']}/{res['cached_tokens']}"
            )

    hw_stats = monitor.stop()

    summary = {
        "engine": engine,
        "model": model,
        "base_url": base_url,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "token_metrics": {
            "avg_prompt_tokens": round(statistics.mean(r["prompt_tokens"] for r in results), 1),
            "avg_completion_tokens": round(statistics.mean(r["completion_tokens"] for r in results), 1),
            "avg_cached_tokens": round(statistics.mean(r["cached_tokens"] for r in results), 1),
            "total_tokens_all_queries": sum(r["total_tokens"] for r in results),
        },
        "speed_metrics": {
            "avg_ttft_ms": round(statistics.mean(r["ttft_ms"] for r in results), 1),
            "min_ttft_ms": round(min(r["ttft_ms"] for r in results), 1),
            "avg_tps": round(statistics.mean(r["tps"] for r in results), 2),
            "max_tps": round(max(r["tps"] for r in results), 2),
            "avg_e2e_s": round(statistics.mean(r["e2e_s"] for r in results), 2),
        },
        "resource_metrics": {
            "vram_idle_mb": loaded_gpu["vram_used_mb"],
            "vram_peak_mb": hw_stats["vram_peak_mb"],
            "vram_total_mb": loaded_gpu["vram_total_mb"],
            "gpu_util_avg_pct": hw_stats["gpu_util_avg_pct"],
            "gpu_util_peak_pct": hw_stats["gpu_util_peak_pct"],
            "gpu_power_avg_w": hw_stats["gpu_power_avg_w"],
            "cpu_avg_pct": hw_stats["cpu_avg_pct"],
            "cpu_peak_pct": hw_stats.get("cpu_peak_pct", hw_stats["cpu_avg_pct"]),
            "ram_avg_mb": hw_stats.get("ram_avg_mb", hw_stats["ram_peak_mb"]),
            "ram_peak_mb": hw_stats["ram_peak_mb"],
        },
        "details": results
    }

    out_file = RESULT_DIR / f"benchmark_result_{engine}.json"
    out_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "=" * 72)
    print(f"🎉 ĐÃ LƯU KẾT QUẢ ĐÁNH GIÁ VÀO: {out_file.resolve()}")
    print("=" * 72)
    print_single_report(summary)
    return summary


def print_single_report(s: Dict[str, Any]):
    tm = s["token_metrics"]
    sm = s["speed_metrics"]
    rm = s["resource_metrics"]
    print(f"\n📋 TÓM TẮT KẾT QUẢ [{s['engine'].upper()} - {s['model']}]:")
    print(f"  1. ĐỘ TỐN TOKEN:")
    print(f"     - Trung bình Input Tokens / câu : {tm['avg_prompt_tokens']} tokens")
    print(f"     - Trung bình Output Tokens / câu: {tm['avg_completion_tokens']} tokens")
    print(f"     - Trung bình Cached Tokens / câu: {tm['avg_cached_tokens']} tokens")
    print(f"     - Tổng Tokens (5 câu test)      : {tm['total_tokens_all_queries']} tokens")
    print(f"  2. TỐC ĐỘ PHẢN HỒI:")
    print(f"     - Độ trễ chữ đầu tiên (TTFT)    : TB {sm['avg_ttft_ms']} ms (Nhanh nhất: {sm['min_ttft_ms']} ms)")
    print(f"     - Tốc độ sinh chữ (Throughput)  : TB {sm['avg_tps']} tokens/s (Đỉnh: {sm['max_tps']} tokens/s)")
    print(f"     - Tổng thời gian trả lời (E2E)  : TB {sm['avg_e2e_s']} giây/câu")
    print(f"  3. ĐỘ TIÊU HAO TÀI NGUYÊN:")
    print(f"     - GPU VRAM (Loaded / Peak)      : {rm['vram_idle_mb']} MB / {rm['vram_peak_mb']} MB (Tổng: {rm['vram_total_mb']} MB)")
    print(f"     - Hiệu suất nhân GPU (TB / Đỉnh): {rm['gpu_util_avg_pct']}% / {rm['gpu_util_peak_pct']}%")
    print(f"     - Điện năng GPU tiêu thụ TB     : {rm['gpu_power_avg_w']} W")
    print(f"     - CPU TB & Hệ thống RAM Đỉnh    : {rm['cpu_avg_pct']}% CPU | {rm['ram_peak_mb']} MB RAM\n")


def compare_all_results():
    engines = ["ollama", "vllm", "sglang"]
    loaded = {}
    for eng in engines:
        p = RESULT_DIR / f"benchmark_result_{eng}.json"
        if p.exists():
            loaded[eng] = json.loads(p.read_text(encoding="utf-8"))

    if not loaded:
        print(f"⚠️ Chưa tìm thấy file benchmark_result_<engine>.json nào trong {RESULT_DIR.resolve()} để so sánh.")
        return

    def val(eng: str, group: str, key: str, suffix: str = "") -> str:
        if eng not in loaded:
            return "*(Chưa đo)*"
        return f"{loaded[eng][group][key]}{suffix}"

    md_lines = [
        "# 📊 BÁO CÁO SO SÁNH HIỆU NĂNG: OLLAMA vs. vLLM vs. SGLANG",
        "",
        "| Nhóm tiêu chí & Chỉ số đo lường | Ollama Local | vLLM Server | SGLang Server |",
        "| :--- | :---: | :---: | :---: |",
        "| **1. ĐỘ TỐN TOKEN (Token Efficiency)** | | | |",
        f"| • Trung bình Input Tokens / câu | {val('ollama', 'token_metrics', 'avg_prompt_tokens')} | {val('vllm', 'token_metrics', 'avg_prompt_tokens')} | {val('sglang', 'token_metrics', 'avg_prompt_tokens')} |",
        f"| • Trung bình Output Tokens / câu | {val('ollama', 'token_metrics', 'avg_completion_tokens')} | {val('vllm', 'token_metrics', 'avg_completion_tokens')} | {val('sglang', 'token_metrics', 'avg_completion_tokens')} |",
        f"| • Cached Tokens tái sử dụng / câu | {val('ollama', 'token_metrics', 'avg_cached_tokens')} | {val('vllm', 'token_metrics', 'avg_cached_tokens')} | {val('sglang', 'token_metrics', 'avg_cached_tokens')} |",
        f"| • Tổng Tokens tiêu thụ (5 kịch bản) | {val('ollama', 'token_metrics', 'total_tokens_all_queries')} | {val('vllm', 'token_metrics', 'total_tokens_all_queries')} | {val('sglang', 'token_metrics', 'total_tokens_all_queries')} |",
        "| **2. TỐC ĐỘ PHẢN HỒI (Response Speed)** | | | |",
        f"| • Độ trễ chữ đầu tiên TB (TTFT) | {val('ollama', 'speed_metrics', 'avg_ttft_ms', ' ms')} | {val('vllm', 'speed_metrics', 'avg_ttft_ms', ' ms')} | {val('sglang', 'speed_metrics', 'avg_ttft_ms', ' ms')} |",
        f"| • TTFT nhanh nhất (Khi trúng Cache) | {val('ollama', 'speed_metrics', 'min_ttft_ms', ' ms')} | {val('vllm', 'speed_metrics', 'min_ttft_ms', ' ms')} | {val('sglang', 'speed_metrics', 'min_ttft_ms', ' ms')} |",
        f"| • Tốc độ sinh chữ TB (Throughput) | {val('ollama', 'speed_metrics', 'avg_tps', ' tok/s')} | {val('vllm', 'speed_metrics', 'avg_tps', ' tok/s')} | {val('sglang', 'speed_metrics', 'avg_tps', ' tok/s')} |",
        f"| • Tổng thời gian trả lời TB (E2E) | {val('ollama', 'speed_metrics', 'avg_e2e_s', ' s')} | {val('vllm', 'speed_metrics', 'avg_e2e_s', ' s')} | {val('sglang', 'speed_metrics', 'avg_e2e_s', ' s')} |",
        "| **3. ĐỘ TIÊU HAO TÀI NGUYÊN (Resource Usage)** | | | |",
        f"| • VRAM khi nạp Model (Idle VRAM) | {val('ollama', 'resource_metrics', 'vram_idle_mb', ' MB')} | {val('vllm', 'resource_metrics', 'vram_idle_mb', ' MB')} | {val('sglang', 'resource_metrics', 'vram_idle_mb', ' MB')} |",
        f"| • VRAM đỉnh khi suy luận (Peak VRAM) | {val('ollama', 'resource_metrics', 'vram_peak_mb', ' MB')} | {val('vllm', 'resource_metrics', 'vram_peak_mb', ' MB')} | {val('sglang', 'resource_metrics', 'vram_peak_mb', ' MB')} |",
        f"| • Tải nhân GPU trung bình / Đỉnh | {val('ollama', 'resource_metrics', 'gpu_util_avg_pct', '%')} | {val('vllm', 'resource_metrics', 'gpu_util_avg_pct', '%')} | {val('sglang', 'resource_metrics', 'gpu_util_avg_pct', '%')} |",
        f"| • Điện năng GPU tiêu thụ TB | {val('ollama', 'resource_metrics', 'gpu_power_avg_w', ' W')} | {val('vllm', 'resource_metrics', 'gpu_power_avg_w', ' W')} | {val('sglang', 'resource_metrics', 'gpu_power_avg_w', ' W')} |",
        f"| • CPU trung bình / Đỉnh | {val('ollama', 'resource_metrics', 'cpu_avg_pct', '%')} | {val('vllm', 'resource_metrics', 'cpu_avg_pct', '%')} | {val('sglang', 'resource_metrics', 'cpu_avg_pct', '%')} |",
        f"| • Hệ thống RAM Đỉnh (Peak RAM) | {val('ollama', 'resource_metrics', 'ram_peak_mb', ' MB')} | {val('vllm', 'resource_metrics', 'ram_peak_mb', ' MB')} | {val('sglang', 'resource_metrics', 'ram_peak_mb', ' MB')} |",
    ]

    report_text = "\n".join(md_lines)
    report_file = RESULT_DIR / "BENCHMARK_REPORT.md"
    report_file.write_text(report_text, encoding="utf-8")
    print("\n" + report_text + "\n")
    print(f"📄 Đã xuất bảng báo cáo Markdown ra file: {report_file.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark Ollama vs vLLM vs SGLang cho Legal Chatbot")
    parser.add_argument("--engine", choices=["ollama", "vllm", "sglang"], help="Tên engine cần đo")
    parser.add_argument("--url", type=str, default="", help="Base URL của engine")
    parser.add_argument("--model", type=str, default="", help="Tên model")
    parser.add_argument("--compare", action="store_true", help="Xuất bảng Markdown so sánh các kết quả đã đo")
    args = parser.parse_args()

    if args.compare:
        compare_all_results()
        return

    if not args.engine:
        parser.print_help()
        return

    default_urls = {
        "ollama": "http://127.0.0.1:11434",
        "vllm": "http://127.0.0.1:8001/v1",
        "sglang": "http://127.0.0.1:30000/v1",
    }
    default_models = {
        "ollama": "qwen2.5:3b",
        "vllm": "model/Qwen2.5-1.5B-Instruct",
        "sglang": "model/Qwen2.5-1.5B-Instruct",
    }

    base_url = args.url or default_urls[args.engine]
    model = args.model or default_models[args.engine]

    asyncio.run(evaluate_engine(args.engine, base_url, model))
    compare_all_results()


if __name__ == "__main__":
    main()
