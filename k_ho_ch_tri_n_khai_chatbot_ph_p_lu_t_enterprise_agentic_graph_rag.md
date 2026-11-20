# Kế Hoạch Triển Khai Hệ Thống Chatbot Hỏi Đáp Pháp Luật Quy Mô Lớn (Agentic + Graph RAG)

## 1. Mục tiêu & Kiến trúc tổng thể (3-Store Architecture)

Xây dựng hệ thống hỏi đáp và tư vấn pháp luật Việt Nam quy mô lớn (đa lĩnh vực, hàng chục nghìn văn bản quy phạm pháp luật), đáp ứng đồng thời các yêu cầu:

*   **Độ chính xác pháp lý cao:** Giải quyết triệt để bài toán tham chiếu chéo, văn bản hướng dẫn và truy vết chuỗi sửa đổi/bổ sung qua nhiều đời văn bản.
*   **Chống bịa đặt tuyệt đối (Strict Grounding):** Mọi câu trả lời đều dựa trên toàn văn điều luật còn hiệu lực, kèm trích dẫn chính xác đến từng Điểm, Khoản, Điều và Số hiệu văn bản.
*   **Tốc độ Indexing & Query tối ưu:** Không phụ thuộc LLM để trích xuất đồ thị trên toàn bộ văn bản (khắc phục điểm yếu của LightRAG); tách biệt rõ kho lưu trữ gốc, kho tìm kiếm ngữ nghĩa và kho duyệt đồ thị.
*   **Khả năng mở rộng & Đồng bộ tin cậy:** Đảm bảo nhất quán dữ liệu giữa 3 kho lưu trữ thông qua hàng đợi bất đồng bộ (Async Queue/Worker).

### Sơ đồ kiến trúc hệ thống

```text
================================================================================
1. OFFLINE INGESTION & SYNC PIPELINE (Chống lệch dữ liệu 3 kho)
================================================================================
[Nguồn văn bản luật (HTML/Word/PDF)]
        │
        ▼ (Rule-based Parser + Regex + 1 LLM call cục bộ cho Điều khoản thi hành)
[LegalParser] ──► Tách cấu trúc (Văn bản -> Chương -> Điều -> Khoản)
        │         + Chuẩn hóa Deterministic ID (VD: 168_2024_NDCP_DIEU_7)
        │         + Trích xuất Cạnh quan hệ (HUONG_DAN, THAM_CHIEU, SUA_DOI, BAI_BO)
        ▼
[PostgreSQL (Source of Truth)] ──► Lưu toàn văn + sync_status = 'PENDING'
        │
        ▼ (Đẩy sự kiện theo doc_id / article_id)
[Message Queue (Redis + Celery / RabbitMQ)]
        ├────────────────────────────────────┐
        ▼ (Idempotent Worker 1)              ▼ (Idempotent Worker 2)
[Qdrant (Hybrid Search Index)]       [Neo4j (Thin Node Graph DB)]
 • Xóa cũ theo article_id             • Dùng lệnh MERGE theo doc_id/article_id
 • Bơm Contextual Header              • Cập nhật Node mỏng & Cạnh quan hệ
 • Embed (Dense + Sparse BM25)        • Tự động nối "Tham chiếu treo" (Stub Node)
 • Upsert + Filter metadata           • Đổi status node cũ nếu bị sửa đổi/bãi bỏ
        └─────────────────┬──────────────────┘
                          ▼
             Cập nhật PostgreSQL: sync_status = 'SYNCED'

================================================================================
2. ONLINE AGENTIC RAG WORKFLOW (LangGraph - Structured State Graph)
================================================================================
[Câu hỏi người dùng]
        │
        ▼
[Node 1: Router & Query Analyzer]
   ├─ Lối tắt (Direct Lookup): Nếu hỏi đích danh Điều/Văn bản -> Bỏ qua Qdrant
   └─ Tình huống phức tạp: Tách ý nhỏ (tối đa 3) + Viết lại sang thuật ngữ pháp lý
        │
        ▼
[Node 2: Hybrid Search + Reranker (Qdrant)]
   • Lọc mặc định: status == "active" -> Lấy Top 5-8 article_id (Điểm neo)
        │
        ▼
[Node 3: Graph Expansion (Neo4j - Parameterized Cypher)]
   • Truy vết chuỗi sửa đổi (AMENDS/REPLACES) -> Đảm bảo lấy bản mới nhất
   • Mở rộng tham chiếu chéo (REFERENCES, 1-hop) & văn bản hướng dẫn (GUIDES)
        │
        ▼
[Node 4: Batch Full-Text Fetch (PostgreSQL)]
   • 1 truy vấn WHERE article_id IN (...) lấy toàn văn các Điều (Parent Document)
        │
        ▼
[Node 5: Grader & Controlled Loop (max_iterations = 2)]
   ├─ Đủ căn cứ pháp lý -> Chuyển sang Node 6
   ├─ Thiếu quy định liên quan -> Gọi Tool bổ sung (tối đa 1-2 vòng)
   └─ Thiếu dữ kiện từ user -> Trả lời nguyên tắc chung + Hỏi ngược lại user
        │
        ▼
[Node 6: Answer Generator & Citation Enforcer] -> Stream trạng thái & câu trả lời
```

---

## 2. Phân vai dữ liệu & Thiết kế Schema 3 kho

Nguyên tắc cốt lõi: **Mỗi kho chỉ giữ đúng loại dữ liệu mình xử lý tốt nhất**, liên kết với nhau qua mã định danh chuẩn hóa `doc_id` và `article_id`.

| Kho lưu trữ | Vai trò duy nhất | Dữ liệu lưu trữ |
| :--- | :--- | :--- |
| **PostgreSQL** | Kho gốc (Source of Truth) & Dữ liệu ứng dụng | Toàn văn Văn bản/Chương/Điều/Khoản, lịch sử đồng bộ (`sync_status`), lịch sử hội thoại, Agent checkpoints, log đánh giá. |
| **Qdrant** | Tìm kiếm ngữ nghĩa & từ khóa (Tìm điểm neo) | Dense Vector + Sparse Vector (BM25), `article_id`, `doc_id`, `status`, `effective_date`, đoạn `chunk_text` ngắn. |
| **Neo4j** | Duyệt mạng lưới quan hệ pháp lý đa tầng | **Node mỏng (Thin Nodes)** chỉ chứa ID và trạng thái, cùng các Cạnh quan hệ có thuộc tính thời gian. Tuyệt đối không lưu toàn văn điều luật. |

### 2.1. Quy chuẩn mã định danh (Deterministic ID)
Mọi văn bản và điều khoản đều được chuẩn hóa ID từ Số hiệu văn bản để các văn bản nạp trước/sau có thể tự động khớp nhau:
*   `doc_id`: `168_2024_NDCP` (từ *Nghị định số 168/2024/NĐ-CP*)
*   `article_id`: `168_2024_NDCP_DIEU_7` (từ *Điều 7 Nghị định 168/2024/NĐ-CP*)

### 2.2. Schema Neo4j (Thin Node Pattern)
*   **Nodes:**
    *   `(:Document {doc_id, doc_type, domain, issue_date, effective_date, status})`
    *   `(:Article {article_id, doc_id, article_number, effective_date, status})`
    *(Dừng ở mức `Article` để tránh phình số lượng node gấp 5–10 lần).*
*   **Relationships:**
    *   `(:Document)-[:CONTAINS]->(:Article)`
    *   `(:Article)-[:REFERENCES {clause_ref}]->(:Article)` *(tham chiếu chéo)*
    *   `(:Article)-[:AMENDS {effective_date, action_type}]->(:Article)` *(sửa đổi, bổ sung, bãi bỏ từng phần)*
    *   `(:Document)-[:REPLACES {effective_date}]->(:Document)` *(thay thế toàn văn)*
    *   `(:Document)-[:GUIDES]->(:Document)` *(hướng dẫn thi hành)*
*   **Constraints & Indexes bắt buộc (đảm bảo tốc độ lookup $O(1)$):**
    ```cypher
    CREATE CONSTRAINT doc_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE;
    CREATE CONSTRAINT article_id_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.article_id IS UNIQUE;
    CREATE INDEX article_status_idx IF NOT EXISTS FOR (a:Article) ON (a.status);
    ```

### 2.3. Chiến lược Chunking & Payload trên Qdrant
*   **Structure-aware Chunking:**
    *   Nếu một **Điều** dài $\le 600$ tokens: giữ nguyên cả Điều làm 1 chunk.
    *   Nếu một **Điều** dài $> 600$ tokens: tách nhỏ theo từng **Khoản** (kèm các Điểm trực thuộc).
*   **Contextual Header Injection:** Ghép cố định đường dẫn phân cấp vào đầu mỗi chunk trước khi embed:
    > `[Nghị định 168/2024/NĐ-CP | Hiệu lực: 01/01/2025 | Chương II: Hành vi vi phạm | Điều 7 | Khoản 2] Nội dung khoản...`
*   **Payload chuẩn trên Qdrant:**
    ```json
    {
      "article_id": "168_2024_NDCP_DIEU_7",
      "doc_id": "168_2024_NDCP",
      "domain": "giao_thong",
      "clause_number": 2,
      "status": "active",
      "effective_date": "2025-01-01",
      "chunk_text": "[Nghị định 168/2024/NĐ-CP | ...] Phạt tiền từ..."
    }
    ```

---

## 3. Data Pipeline & Cơ chế Đồng bộ 3 kho

### 3.1. Trích xuất quan hệ lai (Tốc độ cao, chi phí thấp)
Thay vì chạy LLM qua từng chunk, phân tách văn bản thành 3 vùng xử lý:
1.  **Vùng đầu văn bản (Phần "Căn cứ...") — Regex:** Bắt số hiệu các văn bản gốc để tạo cạnh `[:GUIDES]`.
2.  **Vùng thân văn bản (Nội dung Điều/Khoản) — Regex:** Bắt các mẫu tham chiếu chuẩn (*"tại Điều X"*, *"khoản Y Điều Z Luật này"*, *"theo Nghị định số..."*) để tạo cạnh `[:REFERENCES]`.
3.  **Vùng cuối văn bản (Điều khoản thi hành) & Điều sửa đổi — 1 LLM Call cục bộ:** Cắt riêng đoạn ngắn này đưa qua model nhỏ (Structured Output) để trích xuất chính xác mảng JSON các cạnh `[:AMENDS]`, `[:REPLACES]`, `[:ABOLISHES]` kèm ngày hiệu lực.

### 3.2. Quy trình cập nhật & Chống lệch dữ liệu (Idempotent Sync)
Mọi thao tác thêm mới hoặc sửa đổi đều đi qua **PostgreSQL trước**, sau đó đẩy job vào **Redis + Celery**:

*   **Khi có Luật mới sửa đổi / bãi bỏ Điều cũ:**
    1.  **PostgreSQL:** Không xóa đè Điều cũ; chuyển `status` Điều cũ thành `amended` / `expired`, thêm bản ghi Điều mới (`active`).
    2.  **Qdrant Worker:** Gọi `set_payload` đổi `status` của các Point thuộc Điều cũ (không cần embed lại); đồng thời chunk, embed và `upsert` các Point của Điều mới.
    3.  **Neo4j Worker:** Dùng `MERGE` tạo node Điều mới và nối cạnh `[:AMENDS]` / `[:REPLACES]` sang node Điều cũ; cập nhật thuộc tính `status` của node Điều cũ.
*   **Khi sửa lỗi chính tả / Parse lại Điều hiện tại:**
    1.  **PostgreSQL:** `UPDATE` nội dung Điều.
    2.  **Qdrant Worker:** **Xóa sạch** toàn bộ Point theo bộ lọc `article_id` (tránh để lại Zombie Chunks khi số lượng Khoản thay đổi), sau đó chunk, embed và `upsert` lại toàn bộ.
    3.  **Neo4j Worker:** Xóa các cạnh `[:REFERENCES]` xuất phát từ `article_id` đó và `MERGE` lại theo danh sách tham chiếu mới.
*   **Xử lý "Tham chiếu treo" (Forward References):** Khi nạp Nghị định mới có tham chiếu đến một Luật chưa có trong DB, lệnh `MERGE (target:Article {article_id: $target_id})` trong Neo4j tự động tạo một **Stub Node** (chưa có thuộc tính đầy đủ). Sau này khi nạp Luật đó, lệnh `MERGE` sẽ khớp đúng `article_id` và điền đầy đủ thuộc tính mà không cần chạy lại pipeline cho Nghị định cũ.

---

## 4. Thiết kế Agentic RAG & Bộ Tool (LangGraph)

Sử dụng **Structured Workflow** với giới hạn cứng `max_iterations = 2`. Tuyệt đối **không dùng Text-to-Cypher** (tránh LLM viết sai cú pháp hoặc quét toàn bộ đồ thị gây treo Neo4j); mọi truy vấn đồ thị được đóng gói thành **Parameterized Cypher Tools**.

### 4.1. Bộ công cụ (Tools) cho Agent

1.  **`search_law(query: str, domain: str = None, status: str = "active", top_k: int = 8)`**
    *   Chạy Hybrid Search (Dense + Sparse BM25) trên Qdrant + `bge-reranker-v2-m3` để trả về danh sách `article_id` điểm neo.
2.  **`get_amendment_chain(article_id: str)` (Neo4j Tool)**
    *   Truy vết chuỗi sửa đổi bắc cầu tối đa 5 đời văn bản để tìm ra phiên bản mới nhất còn hiệu lực:
    ```cypher
    MATCH path = (latest:Article)-[:AMENDS*1..5]->(old:Article {article_id: $article_id})
    WHERE latest.status = 'active'
    RETURN latest.article_id AS latest_id, [r IN relationships(path) | r.effective_date] AS timeline
    LIMIT 5
    ```
3.  **`get_cross_references(article_id: str)` (Neo4j Tool)**
    *   Lấy các điều luật được tham chiếu trực tiếp (giới hạn 1-hop và tối đa 10 node còn hiệu lực để chống tràn context):
    ```cypher
    MATCH (a:Article {article_id: $article_id})-[:REFERENCES]->(ref:Article)
    WHERE ref.status = 'active'
    RETURN ref.article_id AS ref_id
    LIMIT 10
    ```
4.  **`get_guiding_documents(doc_id: str)` (Neo4j Tool)**
    *   Tìm các Nghị định/Thông tư hướng dẫn thi hành còn hiệu lực cho một bộ Luật:
    ```cypher
    MATCH (guide:Document)-[:GUIDES]->(base:Document {doc_id: $doc_id})
    WHERE guide.status = 'active'
    RETURN guide.doc_id AS guide_doc_id, guide.doc_type AS doc_type
    LIMIT 10
    ```
5.  **`fetch_articles_content(article_ids: list[str])` (PostgreSQL Tool)**
    *   Chạy 1 câu `SELECT` dạng batch lấy toàn văn các Điều (Parent Document) để nạp vào context của LLM.

### 4.2. Lối tắt & Kiểm soát trải nghiệm (UX)
*   **Direct Lookup Shortcut:** Nếu Node 1 phát hiện người dùng hỏi đích danh số hiệu văn bản và số điều (VD: *"Điều 7 Nghị định 168/2024"*), hệ thống bỏ qua Qdrant, ghép trực tiếp `article_id` và đi thẳng vào Neo4j (kiểm tra sửa đổi/tham chiếu) + PostgreSQL.
*   **Status Streaming (SSE):** Đẩy trạng thái từng bước ra giao diện (*"Đang tìm quy định liên quan..."* → *"Đang kiểm tra lịch sử sửa đổi trên đồ thị..."* → *"Đang tổng hợp căn cứ pháp lý..."*) để giảm cảm giác chờ đợi.

---

## 5. Đề xuất Tech Stack & Tối ưu Production

| Thành phần | Công nghệ đề xuất | Vai trò & Lưu ý vận hành |
| :--- | :--- | :--- |
| **Backend & API** | Python (FastAPI) | Hỗ trợ `async` và Server-Sent Events (SSE) cho streaming. |
| **Agent Orchestration** | LangGraph | Quản lý state graph, rẽ nhánh, giới hạn cứng số vòng lặp. |
| **Relational DB** | PostgreSQL | Source of Truth, lưu toàn văn điều luật & lịch sử chat. |
| **Vector DB** | Qdrant | Hybrid Search (Dense + Sparse BM25) + Metadata Filtering. |
| **Graph DB** | Neo4j (Community / Enterprise) | Cấu hình giới hạn rõ `heap.max_size` và `pagecache.size` trong Docker để không chiếm RAM của Qdrant. |
| **Queue & Cache** | Redis + Celery | Hàng đợi đồng bộ 3 kho + Cache kết quả duyệt đồ thị của top 10–20% điều luật nóng (tự xóa cache khi có job đồng bộ mới). |
| **Embedding & Reranker** | `BAAI/bge-m3` + `BAAI/bge-reranker-v2-m3` | `bge-m3` hỗ trợ sinh đồng thời Dense & Sparse vector cho tiếng Việt. |
| **LLM** | Gemini 2.5 Flash / GPT-4o-mini (Router, Grader, Extractor) + Gemini 2.5 Pro / Claude Sonnet (Generator) | Tách model nhẹ cho các bước điều phối và model mạnh cho bước lập luận pháp lý cuối cùng. |

---

## 6. Lộ trình triển khai (Roadmap 8 Tuần)

### Giai đoạn 1: Hạ tầng 3 kho & Pipeline Parse dữ liệu (Tuần 1 – 2)
*   **Đầu việc:**
    *   Dựng cụm Docker Compose gồm PostgreSQL, Qdrant, Neo4j (đã cấu hình giới hạn RAM & Constraints), Redis + Celery.
    *   Xây dựng `LegalParser` (Regex tách Điều/Khoản + chuẩn hóa Deterministic ID + script kiểm tra nhảy cóc số Điều).
    *   Xây dựng cơ chế trích xuất cạnh quan hệ (Regex + 1 LLM call cho Điều khoản thi hành).
    *   Nạp thử nghiệm tập dữ liệu chuẩn gồm 50–100 văn bản (ưu tiên Văn bản hợp nhất) thuộc 1–2 lĩnh vực có nhiều quan hệ sửa đổi chéo (VD: Giao thông, Lao động).

### Giai đoạn 2: Hoàn thiện Đồng bộ Idempotent & Baseline RAG (Tuần 3 – 4)
*   **Đầu việc:**
    *   Hoàn thiện Celery Workers đồng bộ PostgreSQL → Qdrant & Neo4j; test kỹ 3 kịch bản: Thêm mới, Sửa đổi/Bãi bỏ văn bản cũ, Sửa lỗi nội dung & Tham chiếu treo.
    *   Xây dựng bộ **Golden Dataset** (100 câu hỏi gồm: Tra cứu trực tiếp, Tình huống đời thường, Tham chiếu chéo, Câu hỏi bẫy về luật đã hết hiệu lực).
    *   Đo lường `Recall@10` của Hybrid Search + Reranker và tối ưu ngưỡng cắt trước khi ghép Agent.

### Giai đoạn 3: Xây dựng Agentic Workflow & Parameterized Cypher Tools (Tuần 5 – 6)
*   **Đầu việc:**
    *   Đóng gói 5 Tools chuẩn hóa (Qdrant, Neo4j Parameterized Cypher, PostgreSQL Batch Fetch).
    *   Triển khai State Graph trên LangGraph (bao gồm lối tắt Direct Lookup, vòng lặp kiểm chứng tối đa 2 bước, và cơ chế hỏi ngược khi thiếu dữ kiện).
    *   Chạy đánh giá lại trên Golden Dataset để đo mức cải thiện ở nhóm câu hỏi tình huống phức tạp và tham chiếu chéo.

### Giai đoạn 4: Tối ưu hiệu năng, UX & Mở rộng dữ liệu (Tuần 7 – 8)
*   **Đầu việc:**
    *   Triển khai Redis Caching cho các truy vấn đồ thị nóng và Semantic Caching cho câu hỏi phổ biến.
    *   Xây dựng giao diện Streaming trạng thái suy luận, gắn liên kết cho phép người dùng bấm vào trích dẫn để xem nguyên văn Điều luật (lấy trực tiếp từ PostgreSQL) và hiển thị thông báo miễn trừ trách nhiệm pháp lý.
    *   Mở rộng nạp dữ liệu sang toàn bộ các lĩnh vực pháp luật mục tiêu và thiết lập lịch chạy Incremental Update định kỳ.

---

## 7. Tiêu chí Đánh giá (Evaluation Metrics) & Quản trị Rủi ro

### Chỉ số mục tiêu
1.  **Retrieval Recall@10:** $\ge 92\%$ (tìm đúng Điều/Khoản gốc trong top 10).
2.  **Graph Resolution Accuracy:** $\ge 95\%$ (truy vết đúng điều khoản sửa đổi mới nhất và các điều khoản tham chiếu cốt lõi).
3.  **Citation Accuracy:** $\ge 98\%$ (trích dẫn khớp 100% số hiệu, số điều và trạng thái còn hiệu lực).
4.  **Faithfulness (Chống bịa đặt):** $\ge 95\%$ (không tự suy diễn mức phạt hay điều kiện ngoài context).
5.  **Latency:** TTFT (hiển thị trạng thái suy luận đầu tiên) $< 2$ giây; tổng thời gian trả lời $< 8$ giây.

### Biện pháp kiểm soát rủi ro cốt lõi
*   **Chống bốc nhầm luật cũ:** Hard-code bộ lọc `status == "active"` trong code của Tool `search_law` và trong câu lệnh Cypher, không phụ thuộc vào việc LLM có nhớ truyền tham số hay không.
*   **Chống nổ Context từ đồ thị:** Luôn đặt `LIMIT` cứng trong mọi câu lệnh Cypher (tối đa 10 node tham chiếu) và chỉ mở rộng 1-hop cho cạnh `REFERENCES` (chỉ cho phép 1..5 hops đối với chuỗi `AMENDS`/`REPLACES` để tìm bản mới nhất).
*   **Chống lỗi Parse trên văn bản cũ:** Thiết lập bước kiểm định tự động (Validation Gate) trước khi đẩy vào queue đồng bộ: cảnh báo ngay nếu phát hiện mất thứ tự Điều (`Điều 1, 2, 4...`), thiếu ngày hiệu lực hoặc số hiệu văn bản không khớp quy chuẩn.