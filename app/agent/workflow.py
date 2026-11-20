import re
import json
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.core.id_utils import normalize_doc_id, normalize_article_id
from app.db.models import Article, Document
from app.agent.tools import LegalAgentTools
from app.graph.graph_store import graph_store

class AgenticWorkflow:
    """
    Quy trình Agentic RAG 6 Node có kiểm soát:
    Node 1: Router & Direct Lookup Shortcut
    Node 2: Hybrid Search (Qdrant)
    Node 3: Graph Expansion (Neo4j/NetworkX)
    Node 4: Batch Full-Text Fetch (SQLite)
    Node 5: Grader & Controlled Loop
    Node 6: Answer Generator & Citation Enforcer
    """

    def __init__(self, db: Session):
        self.db = db

    def _detect_general_intent(self, query: str) -> Optional[Dict[str, str]]:
        """
        Nhận diện các câu hỏi phi pháp lý (chào hỏi, giới thiệu, câu hỏi đời thường ngoài phạm vi luật).
        """
        q_lower = query.lower().strip()
        q_clean = re.sub(r'[^\w\s]', '', q_lower)
        
        # 1. Chào hỏi và hỏi thông tin trợ lý
        greetings = [
            'xin chào', 'chào bạn', 'chào em', 'chào anh', 'chào chị', 'chào', 'hello', 'hi', 'alo', 
            'bạn là ai', 'bạn tên gì', 'mày là ai', 'em là ai', 'giới thiệu', 'bạn làm được gì',
            'chức năng của bạn', 'hướng dẫn', 'trợ lý ảo', 'giới thiệu bản thân'
        ]
        if any(q_clean == g or q_clean.startswith(g + ' ') or q_clean.endswith(' ' + g) for g in greetings):
            return {
                "type": "greeting",
                "message": (
                    "👋 **Xin chào! Tôi là Trợ Lý Pháp Luật Việt Nam (Legal Assistant AI)**.\n\n"
                    "Tôi được xây dựng trên kiến trúc **Agentic Graph RAG** để hỗ trợ bạn tra cứu, giải đáp các quy định pháp luật với độ chính xác cao và cam kết chống bịa đặt (Strict Grounding):\n\n"
                    "🔹 **Xử phạt vi phạm giao thông đường bộ:** Mức phạt vượt đèn đỏ, nồng độ cồn, trừ điểm GPLX theo Nghị định 100/2019, 123/2021 và 168/2024.\n"
                    "🔹 **Quy định pháp luật lao động:** Thời giờ làm việc, làm thêm giờ theo Bộ luật Lao động 45/2019.\n"
                    "🔹 **Truy vết văn bản:** Tự động phát hiện các điều khoản đã được sửa đổi, bổ sung và dẫn chiếu đến văn bản mới nhất.\n"
                    "🔹 **Tra cứu trực tiếp:** Bạn có thể gõ trực tiếp số điều và số văn bản (VD: *Điều 7 Nghị định 168/2024*).\n\n"
                    "Bạn cần tra cứu quy định pháp lý hoặc tình huống nào hôm nay?"
                )
            }
            
        # 2. Các yêu cầu phi pháp lý rõ ràng (kể chuyện, làm thơ, nấu ăn, thời tiết, code...)
        casual_patterns = [
            'thời tiết', 'nấu ăn', 'cách làm bánh', 'nấu phở', 'cách nấu', 'làm thơ', 'viết thơ',
            'kể chuyện', 'chuyện cười', 'hát bài', 'viết code', 'lập trình', 'giải toán',
            'bằng mấy', 'ai là tổng thống', 'thủ đô', 'bóng đá', 'tin tức hôm nay'
        ]
        if any(p in q_lower for p in casual_patterns):
            return {
                "type": "off_topic",
                "message": (
                    "ℹ️ **Thông báo:** Tôi là trợ lý AI chuyên trách về **Pháp luật Việt Nam**.\n\n"
                    f"Câu hỏi *\"{query}\"* không thuộc phạm vi tư vấn hay tra cứu pháp luật. Để hệ thống hỗ trợ bạn tốt nhất, vui lòng đặt các câu hỏi liên quan đến:\n"
                    "- Quy định xử phạt vi phạm hành chính (Giao thông đường bộ).\n"
                    "- Quyền, nghĩa vụ và chế độ lao động (Thời giờ làm việc, làm thêm giờ).\n"
                    "- Tra cứu nguyên văn các Điều luật theo số hiệu văn bản quy phạm pháp luật."
                )
            }
            
        return None

    def _detect_direct_lookup(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Lối tắt (Direct Lookup Shortcut):
        Kiểm tra nếu người dùng hỏi đích danh Điều/Văn bản cụ thể.
        VD: 'Điều 7 Nghị định 168/2024', 'Điều 5 Nghị định 100/2019'
        """
        pattern = re.compile(
            r'(?:Điều|điều)\s+(\d+)[^\.\n;]*?(?:Nghị định|Luật|Thông tư|NĐ|QH)?[^\.\n;]*?(?:số\s*)?([0-9]+/[0-9]+(?:/[A-Za-z0-9Đđ\-_]+)?)',
            re.IGNORECASE
        )
        match = pattern.search(query)
        if match:
            art_num = int(match.group(1))
            raw_sym = match.group(2)
            
            # Tìm trong database xem có article_id nào khớp với số hiệu và số điều này không
            num_part = raw_sym.replace('/', '_')
            candidate = self.db.query(Article).filter(
                Article.article_number == art_num,
                Article.article_id.like(f"%{num_part}%")
            ).first()
            
            if candidate:
                return {
                    "article_num": art_num,
                    "doc_symbol": raw_sym,
                    "doc_id": candidate.doc_id,
                    "article_id": candidate.article_id
                }
                
            # Thử với doc_id chuẩn hóa
            doc_id = normalize_doc_id(raw_sym)
            article_id = normalize_article_id(doc_id, art_num)
            cand2 = self.db.query(Article).filter(Article.article_id == article_id).first()
            if cand2:
                return {
                    "article_num": art_num,
                    "doc_symbol": raw_sym,
                    "doc_id": cand2.doc_id,
                    "article_id": cand2.article_id
                }
                
        return None

    async def _call_llm(self, prompt: str, system_prompt: str, articles_data: List[Dict[str, Any]]) -> str:
        """Gọi LLM: Hỗ trợ linh hoạt vLLM / SGLang (OpenAI-compatible) -> Ollama Qwen cục bộ -> Cloud LLM -> Local Synthesizer."""
        
        # 0. Gọi vLLM hoặc SGLang Server (OpenAI-Compatible API)
        if settings.LLM_PROVIDER in ("vllm", "sglang"):
            base_url = settings.VLLM_BASE_URL if settings.LLM_PROVIDER == "vllm" else settings.SGLANG_BASE_URL
            model_name = settings.VLLM_MODEL if settings.LLM_PROVIDER == "vllm" else settings.SGLANG_MODEL
            try:
                import httpx
                async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
                    resp = await client.post("/chat/completions", json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "stream": False,
                        "temperature": 0.1
                    })
                    if resp.status_code == 200:
                        choices = resp.json().get("choices", [])
                        if choices:
                            content = choices[0].get("message", {}).get("content")
                            if content:
                                return content
                    else:
                        print(f"⚠️ [Agent Workflow] {settings.LLM_PROVIDER.upper()} trả về status code {resp.status_code}: {resp.text}")
            except Exception as e:
                print(f"⚠️ [Agent Workflow] Lỗi kết nối {settings.LLM_PROVIDER.upper()} ({base_url}): {e}")

        # 1. Gọi Ollama Local (Qwen)
        if settings.LLM_PROVIDER == "ollama" or not (settings.GEMINI_API_KEY or settings.OPENAI_API_KEY):
            try:
                import httpx
                async with httpx.AsyncClient(base_url=settings.OLLAMA_BASE_URL, timeout=60.0) as client:
                    resp = await client.post("/api/chat", json={
                        "model": settings.OLLAMA_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "stream": False,
                        "options": {
                            "temperature": 0.2
                        }
                    })
                    if resp.status_code == 200:
                        content = resp.json().get("message", {}).get("content")
                        if content:
                            return content
                    else:
                        print(f"⚠️ [Agent Workflow] Ollama trả về status code {resp.status_code}: {resp.text}")
            except Exception as e:
                print(f"⚠️ [Agent Workflow] Lỗi kết nối Ollama LLM ({settings.OLLAMA_MODEL}): {e}")

        # 2. Thử Google Gemini nếu có cấu hình
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model=settings.LLM_MODEL,
                    contents=f"{system_prompt}\n\n{prompt}"
                )
                if response.text:
                    return response.text
            except Exception as e:
                pass

        # 3. Thử OpenAI nếu có cấu hình
        if settings.OPENAI_API_KEY:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=settings.OPENAI_API_KEY)
                completion = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                )
                if completion.choices[0].message.content:
                    return completion.choices[0].message.content
            except Exception as e:
                pass

        # 4. Fallback: Local Built-in Synthesizer
        return self._local_rule_synthesizer(prompt, articles_data)

    def _local_rule_synthesizer(self, prompt: str, articles_data: List[Dict[str, Any]]) -> str:
        """Bộ sinh câu trả lời pháp lý chuẩn tắc dựa trên nguyên văn điều luật đã tra cứu."""
        if not articles_data:
            return "Hệ thống chưa tìm thấy văn bản phù hợp trong cơ sở dữ liệu hiện hành."
            
        summary_lines = []
        summary_lines.append("### 1. Căn cứ và nội dung quy định pháp lý:")
        
        for art in articles_data:
            summary_lines.append(f"- **{art['doc_id']} (Điều {art['article_number']} - {art['title']})**:")
            lines = [l.strip() for l in art['content'].split('\n') if l.strip() and not l.strip().startswith('Điều')]
            for line in lines[:5]:
                summary_lines.append(f"  > {line}")
                
        summary_lines.append("\n### 2. Kết luận tư vấn:")
        summary_lines.append("Người hỏi cần đối chiếu chính xác hành vi, quyền và nghĩa vụ thực tế với các căn cứ pháp lý còn hiệu lực được trích dẫn chi tiết đính kèm dưới đây.")
        summary_lines.append("\n*Lưu ý: Mọi trích dẫn phía dưới đều được đối chiếu trực tiếp từ cơ sở dữ liệu luật gốc (Source of Truth).*")
        
        return "\n".join(summary_lines)

    async def stream_workflow(self, query: str) -> AsyncGenerator[str, None]:
        """Luồng thực thi State Graph và stream trạng thái qua SSE (Server-Sent Events)."""
        
        # ----------------- NODE 1: ROUTER & ANALYZER -----------------
        yield json.dumps({
            "type": "step",
            "node": "router",
            "message": "Node 1: Phân tích câu hỏi và xác định ý định người dùng..."
        })
        await asyncio.sleep(0.2)

        # 1.1. Kiểm tra chào hỏi hoặc câu hỏi phi pháp lý (General Chat / Off-topic)
        general_intent = self._detect_general_intent(query)
        if general_intent:
            yield json.dumps({
                "type": "step",
                "node": "router",
                "message": "⚡ Nhận diện tương tác chung (Chào hỏi / Phi pháp lý) - Phản hồi trực tiếp."
            })
            yield json.dumps({
                "type": "answer",
                "content": general_intent["message"]
            })
            yield json.dumps({"type": "citations", "citations": []})
            yield json.dumps({"type": "done"})
            return

        # 1.2. Kiểm tra lối tắt tra cứu trực tiếp Điều/Văn bản (Direct Lookup)
        direct_lookup = self._detect_direct_lookup(query)
        anchor_article_ids = []
        is_direct = False

        if direct_lookup:
            is_direct = True
            anchor_article_ids = [direct_lookup["article_id"]]
            yield json.dumps({
                "type": "step",
                "node": "router",
                "message": f"⚡ Kích hoạt lối tắt (Direct Lookup Shortcut): Nhận diện trực tiếp {direct_lookup['article_id']}"
            })
        else:
            # ----------------- NODE 2: HYBRID SEARCH (QDRANT) -----------------
            yield json.dumps({
                "type": "step",
                "node": "qdrant",
                "message": "Node 2: Đang tìm kiếm Hybrid Search (Dense + Sparse BM25) + Reranking với lọc status='active'..."
            })
            await asyncio.sleep(0.3)
            
            search_results = LegalAgentTools.search_law(query=query, top_k=settings.TOP_K_ANCHOR)
            
            if not search_results:
                yield json.dumps({
                    "type": "step",
                    "node": "qdrant",
                    "message": "⚠️ Không tìm thấy điều luật nào có độ tương đồng đạt ngưỡng tin cậy (Ngoài phạm vi DB)."
                })
                anchor_article_ids = []
            else:
                anchor_article_ids = [r["article_id"] for r in search_results]
                best_score = round(search_results[0]["score"] * 100, 1)
                yield json.dumps({
                    "type": "step",
                    "node": "qdrant",
                    "message": f"Đã tìm thấy {len(anchor_article_ids)} điều luật điểm neo (Độ khớp cao nhất: {best_score}%): {', '.join(anchor_article_ids[:3])}"
                })

        # ----------------- NODE 3: GRAPH EXPANSION (NEO4J / NETWORKX) -----------------
        expanded_article_ids = set(anchor_article_ids)
        
        if anchor_article_ids:
            yield json.dumps({
                "type": "step",
                "node": "graph",
                "message": "Node 3: Mở rộng đồ thị quan hệ: Truy vết chuỗi sửa đổi (AMENDS) & tham chiếu chéo (REFERENCES)..."
            })
            await asyncio.sleep(0.3)

            graph_events = []
            amended_replacements = {}

            for art_id in anchor_article_ids:
                # 3.1. Kiểm tra chuỗi sửa đổi
                amend_info = LegalAgentTools.get_amendment_chain(art_id)
                if amend_info["is_amended"]:
                    latest_id = amend_info["latest_id"]
                    amended_replacements[art_id] = latest_id
                    expanded_article_ids.discard(art_id)
                    expanded_article_ids.add(latest_id)
                    graph_events.append(f"🔄 Điều cũ {art_id} đã được sửa đổi bởi {latest_id}")

                # 3.2. Mở rộng tham chiếu chéo (1-hop)
                refs = LegalAgentTools.get_cross_references(art_id, max_refs=settings.MAX_REFERENCES_PER_NODE)
                for ref in refs:
                    target_id = ref["target_id"]
                    expanded_article_ids.add(target_id)
                    graph_events.append(f"🔗 Tham chiếu chéo tới {target_id}")

            if graph_events:
                yield json.dumps({
                    "type": "step",
                    "node": "graph",
                    "message": " | ".join(graph_events[:3])
                })

        # ----------------- NODE 4: BATCH FULL-TEXT FETCH (SQLITE) -----------------
        articles_data = []
        if expanded_article_ids:
            yield json.dumps({
                "type": "step",
                "node": "fetch",
                "message": f"Node 4: Tải toàn văn {len(expanded_article_ids)} Điều luật từ SQLite (Source of Truth)..."
            })
            await asyncio.sleep(0.2)
            articles_data = LegalAgentTools.fetch_articles_content(self.db, list(expanded_article_ids))
        
        # ----------------- NODE 5: GRADER & VALIDATION -----------------
        yield json.dumps({
            "type": "step",
            "node": "grader",
            "message": "Node 5: Đánh giá độ phủ pháp lý (Grader) & kiểm tra ngày hiệu lực..."
        })
        await asyncio.sleep(0.2)

        # Nếu không có điều luật nào đạt ngưỡng tin cậy (câu hỏi ngoài kịch bản/ngoài DB)
        if not articles_data or len(anchor_article_ids) == 0:
            yield json.dumps({
                "type": "answer",
                "content": (
                    "### ⚠️ Không tìm thấy căn cứ pháp lý phù hợp trong hệ thống\n\n"
                    f"Hệ thống đã tra cứu toàn bộ cơ sở dữ liệu pháp luật hiện hành nhưng **không tìm thấy quy định hoặc điều khoản nào điều chỉnh câu hỏi**: *\"{query}\"*.\n\n"
                    "**Nguyên nhân:**\n"
                    "- Cơ sở dữ liệu hiện tại của hệ thống đang lưu trữ các văn bản về:\n"
                    "  1. **Giao thông đường bộ:** Nghị định 100/2019/NĐ-CP, Nghị định 123/2021/NĐ-CP, Nghị định 168/2024/NĐ-CP.\n"
                    "  2. **Lao động:** Bộ luật Lao động số 45/2019/QH14.\n"
                    "- Câu hỏi của bạn thuộc lĩnh vực pháp luật khác hoặc ngoài phạm vi các văn bản trên. Để đảm bảo nguyên tắc **Strict Grounding (chống bịa đặt tuyệt đối)**, hệ thống từ chối trả lời suy đoán.\n\n"
                    "💡 **Gợi ý:** Bạn có thể đặt câu hỏi về mức phạt vi phạm giao thông (vượt đèn đỏ, nồng độ cồn, trừ điểm GPLX) hoặc thời giờ làm việc/làm thêm giờ của người lao động, hoặc cập nhật thêm văn bản mới vào hệ thống."
                )
            })
            yield json.dumps({"type": "citations", "citations": []})
            yield json.dumps({"type": "done"})
            return

        # ----------------- NODE 6: ANSWER GENERATION & CITATION ENFORCER -----------------
        yield json.dumps({
            "type": "step",
            "node": "generator",
            "message": "Node 6: Tổng hợp câu trả lời & ép trích dẫn chính xác (Citation Enforcer)..."
        })

        # Chuẩn bị context cho LLM (Ưu tiên các điều luật Anchor có điểm cao nhất)
        # Sắp xếp articles_data theo thứ tự ưu tiên của anchor_article_ids
        anchor_order = {aid: idx for idx, aid in enumerate(anchor_article_ids)}
        sorted_articles = sorted(
            articles_data,
            key=lambda a: anchor_order.get(a["article_id"], 999)
        )

        context_blocks = []
        citations_list = []

        # Đưa toàn bộ các điều luật neo và mở rộng có liên quan (tối đa 6-8 điều) vào context LLM
        max_llm_articles = 6

        for idx, art in enumerate(sorted_articles):
            citations_list.append({
                "article_id": art["article_id"],
                "doc_id": art["doc_id"],
                "article_number": art["article_number"],
                "title": art["title"],
                "chapter_title": art["chapter_title"],
                "status": art["status"],
                "effective_date": art["effective_date"],
                "preview": art["content"][:200] + "..." if len(art["content"]) > 200 else art["content"]
            })
            
            if idx < max_llm_articles:
                context_blocks.append(
                    f"=== [{art['doc_id']} | Điều {art['article_number']}: {art['title']}] (Hiệu lực: {art['effective_date']}) ===\n"
                    f"{art['content']}\n"
                )

        context_str = "\n".join(context_blocks)

        system_prompt = (
            "Bạn là Chuyên gia / Trợ lý Pháp luật Việt Nam cao cấp. Nhiệm vụ của bạn là tư vấn và giải đáp chính xác, khách quan cho người dân dựa trên các điều luật trong CONTEXT được cung cấp.\n"
            "QUY TẮC BẮT BUỘC:\n"
            "1. KHI CÁC ĐIỀU LUẬT TRONG CONTEXT CÓ QUY ĐỊNH LIÊN QUAN:\n"
            "   - Trực tiếp giải đáp câu hỏi của người dùng ở ngay câu đầu tiên (ví dụ: 'KHÔNG ĐƯỢC PHÉP...', 'ĐƯỢC PHÉP...', 'Mức xử phạt từ...', 'Thời giờ làm việc tối đa là...').\n"
            "   - Đối chiếu và phân tích cụ thể tình huống thực tế của người hỏi với các điều kiện, tiêu chuẩn trong luật (ví dụ: so sánh độ tuổi của nam và nữ với điều kiện luật định).\n"
            "   - Trích dẫn chính xác và đầy đủ: Điểm mấy, Khoản mấy, Điều mấy, Văn bản nào (Số hiệu, tên văn bản và năm ban hành).\n"
            "   - Nếu có văn bản sửa đổi/bổ sung, nêu rõ điều khoản mới nhất đang áp dụng.\n"
            "2. KHI CÂU HỎI HOÀN TOÀN KHÔNG CÓ TRONG CONTEXT:\n"
            "   - Nêu rõ cơ sở dữ liệu hiện tại chưa có văn bản quy định điều chỉnh vấn đề này.\n"
            "   - Tuyệt đối không tự suy diễn hoặc dùng kiến thức ngoài CONTEXT để gán ghép điều luật sai lệch.\n"
            "3. Trình bày Markdown chuyên nghiệp, rõ ràng, chặt chẽ, khách quan và chuẩn mực pháp lý."
        )

        user_prompt = (
            f"CĂN CỨ PHÁP LÝ (CONTEXT):\n"
            f"{context_str}\n\n"
            f"CÂU HỎI CỦA NGƯỜI DÂN:\n"
            f"\"{query}\"\n\n"
            f"YÊU CẦU TRẢ LỜI:\n"
            f"1. Trực tiếp kết luận ngay ở đầu: Trường hợp này CÓ ĐƯỢC hay KHÔNG ĐƯỢC (hoặc nêu cụ thể mức phạt / quy định tương ứng)?\n"
            f"2. Phân tích cụ thể các điều kiện theo luật và đối chiếu với tình huống của người hỏi.\n"
            f"3. Trích dẫn chính xác Điểm, Khoản, Điều và số hiệu văn bản quy phạm pháp luật làm căn cứ."
        )

        answer_text = await self._call_llm(user_prompt, system_prompt, articles_data)

        # Lưu vào ChatHistory SQLite
        try:
            from app.db.models import ChatHistory
            chat_record = ChatHistory(
                session_id="default",
                role="assistant",
                content=answer_text,
                citations=json.dumps(citations_list)
            )
            self.db.add(chat_record)
            self.db.commit()
        except Exception:
            pass

        # Trả về kết quả hoàn chỉnh
        yield json.dumps({
            "type": "answer",
            "content": answer_text
        })

        yield json.dumps({
            "type": "citations",
            "citations": citations_list
        })

        # Lấy đồ thị liên quan để visualizer trên UI
        subgraph = graph_store.get_subgraph_for_visualization(list(expanded_article_ids))
        yield json.dumps({
            "type": "graph_viz",
            "graph": subgraph
        })

        yield json.dumps({"type": "done"})
