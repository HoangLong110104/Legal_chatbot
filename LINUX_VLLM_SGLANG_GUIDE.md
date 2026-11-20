# 🐧 Hướng Dẫn Triển Khai & Đánh Giá Legal Chatbot Trên Linux (Ollama vs. vLLM vs. SGLang)

Tài liệu này hướng dẫn chi tiết từng bước cách chuyển dự án **Hệ Thống Trợ Lý Pháp Luật Việt Nam (Agentic Graph RAG)** từ Windows sang máy **Linux (Ubuntu/Debian)** để chạy ứng dụng và đánh giá hiệu năng giữa 3 Engine: **Ollama Local**, **vLLM Server** và **SGLang Server**.

---

## 1. Cấu trúc thư mục cần copy sang máy Linux

 khi nén dự án từ Windows mang sang Linux, bạn chỉ cần giữ các thư mục sau (bỏ qua thư mục `venv/` của Windows):

```text
legal_chatbot/
├── app/                          # Toàn bộ mã nguồn Backend & Giao diện Web
├── data/
│   ├── legal.db                  # Cơ sở dữ liệu SQLite (đã có sẵn các luật đã nạp)
│   └── qdrant_local/             # Vector DB cục bộ (đã có sẵn vector embeddings)
├── model/
│   ├── multilingual-e5-small/    # Model Embedding cục bộ (384-dim)
│   ├── bge-reranker-v2-m3/       # Model Cross-Encoder Reranker cục bộ
│   └── Qwen2.5-1.5B-Instruct/    # Model LLM chuẩn HuggingFace dùng chung cho vLLM & SGLang
├── result/                       # Thư mục lưu kết quả đánh giá (JSON & Báo cáo Markdown)
├── benchmark_eval.py             # Công cụ tự động đo Token, Tốc độ và Tài nguyên
├── requirements.txt              # Các thư viện Python của dự án
└── run.py                        # Điểm khởi chạy Web Server FastAPI
```

> **Lưu ý:** Toàn bộ dữ liệu pháp luật bạn đã nạp trên Windows nằm trong `data/` sẽ được giữ nguyên 100%, sang Linux **không cần nạp (ingest) lại**.

---

## 2. Cài đặt môi trường cơ bản cho Project trên Linux

Mở Terminal trên máy Linux tại thư mục `legal_chatbot`:

```bash
# 1. Cập nhật gói hệ thống và cài đặt Python venv + công cụ build cơ bản
sudo apt update && sudo apt install -y python3-venv python3-pip python3-dev build-essential curl

# 2. Tạo môi trường ảo (Virtual Environment) mới cho Linux
python3 -m venv venv
source venv/bin/activate

# 3. Cài đặt các thư viện của dự án + thư viện đo tài nguyên psutil
pip install --upgrade pip
pip install -r requirements.txt
pip install psutil huggingface_hub
```

---

## 3. Hướng dẫn cài đặt & khởi chạy 3 Engine trên Linux (Chế độ CPU - Không có GPU NVIDIA)

Để kết quả so sánh công bằng 1:1 giữa 3 bên, cả 3 Engine đều sẽ chạy mô hình **`Qwen2.5-1.5B-Instruct`**.
*(Lưu ý: Chạy lần lượt từng Engine, đo xong Engine nào thì tắt đi trước khi bật Engine tiếp theo để không bị tranh chấp RAM/CPU).*

---

### 🟢 ĐỢT 1: Chạy và đo với Ollama Local

#### Bước 1.1: Cài đặt Ollama trên Linux & kéo model `qwen2.5:1.5b`
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:1.5b
```

#### Bước 1.2: Chạy đo Benchmark cho Ollama
```bash
source venv/bin/activate
python3 benchmark_eval.py --engine ollama --model qwen2.5:1.5b
```
* **Kết quả lưu tại:** `result/benchmark_result_ollama.json`

#### Bước 1.3: Dừng Ollama để giải phóng RAM cho đợt đo tiếp theo
```bash
sudo systemctl stop ollama
# Hoặc nếu chạy thủ công: pkill ollama
```

---

### 🔵 ĐỢT 2: Chạy và đo với vLLM Server (CPU Mode)

Vì máy Linux không có GPU NVIDIA, vLLM cần chạy bản biên dịch dành cho **CPU Backend**. Có 2 cách chạy vLLM CPU trên Linux:

#### Cách A: Dùng Docker vLLM CPU (Nhanh và ít lỗi phụ thuộc nhất)
```bash
# Build hoặc chạy container vLLM CPU gắn trực tiếp thư mục model của dự án
docker run --rm -it \
    --network host \
    -v $(pwd)/model:/models \
    -e VLLM_CPU_KVCACHE_SPACE=4 \
    vllm/vllm-openai-cpu:latest \
    --model /models/Qwen2.5-1.5B-Instruct \
    --dtype bfloat16 \
    --max-model-len 4096 \
    --port 8001
```

#### Cách B: Cài trực tiếp vLLM CPU từ mã nguồn trong môi trường Python riêng
```bash
python3 -m venv venv_vllm
source venv_vllm/bin/activate

# Cài PyTorch CPU và build vLLM cho CPU
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
git clone https://github.com/vllm-project/vllm.git
cd vllm
pip install -v -r requirements/cpu.txt --extra-index-url https://download.pytorch.org/whl/cpu
VLLM_TARGET_DEVICE=cpu python3 setup.py install
cd ..

# Khởi chạy vLLM Server trên cổng 8001
export VLLM_CPU_KVCACHE_SPACE=4
python3 -m vllm.entrypoints.openai.api_server \
    --model ./model/Qwen2.5-1.5B-Instruct \
    --device cpu \
    --dtype bfloat16 \
    --max-model-len 4096 \
    --port 8001
```

#### Bước 2.2: Mở Terminal thứ 2 để chạy đo Benchmark cho vLLM
```bash
source venv/bin/activate
python3 benchmark_eval.py \
    --engine vllm \
    --url http://127.0.0.1:8001/v1 \
    --model ./model/Qwen2.5-1.5B-Instruct
```
*(Nếu dùng Docker ở Cách A thì truyền `--model /models/Qwen2.5-1.5B-Instruct`)*.
* **Kết quả lưu tại:** `result/benchmark_result_vllm.json`
* **Sau khi đo xong:** Nhấn `Ctrl + C` ở Terminal vLLM để tắt server và giải phóng RAM.

---

### 🟣 ĐỢT 3: Chạy và đo với SGLang Server (CPU Mode)

#### Bước 3.1: Cài đặt và khởi chạy SGLang Server trên CPU
```bash
python3 -m venv venv_sglang
source venv_sglang/bin/activate

pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install "sglang[all]"

# Khởi chạy SGLang Server ở chế độ CPU trên cổng 30000
python3 -m sglang.launch_server \
    --model-path ./model/Qwen2.5-1.5B-Instruct \
    --device cpu \
    --dtype bfloat16 \
    --context-length 4096 \
    --port 30000 \
    --disable-overlap-schedule
```

#### Bước 3.2: Mở Terminal thứ 2 để chạy đo Benchmark cho SGLang
```bash
source venv/bin/activate
python3 benchmark_eval.py \
    --engine sglang \
    --url http://127.0.0.1:30000/v1 \
    --model ./model/Qwen2.5-1.5B-Instruct
```
* **Kết quả lưu tại:** `result/benchmark_result_sglang.json`
* **Sau khi đo xong:** Nhấn `Ctrl + C` ở Terminal SGLang để tắt server.

---

## 4. Xuất Báo Cáo Tổng Hợp So Sánh 3 Engine

Khi trong thư mục `result/` đã có các file kết quả (`benchmark_result_ollama.json`, `benchmark_result_vllm.json`, `benchmark_result_sglang.json`), bạn chạy lệnh sau để xuất bảng báo cáo tổng hợp:

```bash
source venv/bin/activate
python3 benchmark_eval.py --compare
```

Hệ thống sẽ tự động tạo file **[result/BENCHMARK_REPORT.md](result/BENCHMARK_REPORT.md)** bao gồm bảng Markdown chuẩn so sánh đủ 3 nhóm tiêu chí:
1. **Độ tốn Token:** Trung bình Input Tokens, Output Tokens, Cached Tokens tái sử dụng, Tổng Tokens.
2. **Tốc độ phản hồi:** Độ trễ chữ đầu tiên (TTFT - ms), Tốc độ sinh chữ (Throughput - tokens/s), Tổng thời gian hoàn tất (E2E - giây).
3. **Độ tiêu hao tài nguyên:** CPU trung bình/đỉnh (%), Hệ thống RAM đỉnh (MB), và GPU VRAM/Power (nếu chạy trên máy có GPU).

---

## 5. Cách chạy Giao diện Web Legal Chatbot với vLLM hoặc SGLang

Ngoài việc chạy script đo tự động, nếu bạn muốn mở trực tiếp **Giao diện Web Chatbot (`http://127.0.0.1:8000`)** sử dụng vLLM hoặc SGLang làm bộ não trả lời:

1. Mở hoặc tạo file `.env` tại thư mục gốc `legal_chatbot/`:
   ```env
   # Chọn 1 trong 3: ollama | vllm | sglang
   LLM_PROVIDER=vllm

   # Cấu hình cho Ollama
   OLLAMA_BASE_URL=http://127.0.0.1:11434
   OLLAMA_MODEL=qwen2.5:1.5b

   # Cấu hình cho vLLM
   VLLM_BASE_URL=http://127.0.0.1:8001/v1
   VLLM_MODEL=./model/Qwen2.5-1.5B-Instruct

   # Cấu hình cho SGLang
   SGLANG_BASE_URL=http://127.0.0.1:30000/v1
   SGLANG_MODEL=./model/Qwen2.5-1.5B-Instruct
   ```

2. Khởi chạy Web Server:
   ```bash
   source venv/bin/activate
   python3 run.py
   ```
3. Mở trình duyệt truy cập: `http://127.0.0.1:8000`
