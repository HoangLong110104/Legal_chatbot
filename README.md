# Hệ Thống Trợ Lý Pháp Luật Việt Nam (Enterprise Agentic + Graph RAG)

Hệ thống hỏi đáp và tư vấn pháp luật Việt Nam quy mô lớn, giải quyết triệt để bài toán chống bịa đặt (Strict Grounding) và tự động truy vết chuỗi văn bản sửa đổi/bổ sung, văn bản hướng dẫn và tham chiếu chéo.

Hệ thống chạy **100% Cục Bộ (Zero-Docker & Full Local AI)**:
*   **LLM Engine:** Mô hình **Qwen** chạy trên máy chủ **Ollama Local** (`qwen2.5:3b` hoặc `qwen3.5:9b`).
*   **Ingest Embedding:** Mô hình cục bộ **`multilingual-e5-small`** (384 chiều, chuẩn hóa `passage:` / `query:`).
*   **Cross-Encoder Reranker:** Mô hình cục bộ **`BAAI/bge-reranker-v2-m3`** chấm điểm lại mức độ phù hợp ngữ nghĩa sâu.
*   **Kho gốc (Source of Truth):** **SQLite** (`data/legal.db`) lưu toàn văn Văn bản, Điều, Khoản.
*   **Kho tìm kiếm ngữ nghĩa:** **Qdrant Local** (`data/qdrant_local/`) chạy embedded kết hợp Dense Vector + BM25 Lexical + Hard filter `status == 'active'`.
*   **Kho đồ thị pháp lý:** **NetworkX Engine** kết hợp bảng `relationships` trong SQLite, mô phỏng chuẩn xác Parameterized Cypher (`get_amendment_chain`, `get_cross_references`, `get_guiding_documents`).
*   **Giao diện:** Web UI hiện đại (Dark & Deep Navy aesthetic), Server-Sent Events (SSE) streaming quá trình suy luận, xem trước toàn văn điều luật qua Drawer trượt và quản lý cấu hình mô hình trực tiếp.

---

## 1. Khởi động nhanh (Quick Start)

### Cách 1: Chạy file batch (Khuyên dùng trên Windows)
Nhấp đúp chuột vào file:
```cmd
start.bat
```

### Cách 2: Khởi chạy bằng lệnh
```powershell
.\venv\Scripts\python.exe run.py
```

Truy cập giao diện Web tại: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 2. Các mô hình AI cục bộ đang hoạt động

1. **Embedding (`model/multilingual-e5-small`):**
   * Tự động sinh vector 384 chiều cho toàn bộ Điều/Khoản luật và câu hỏi người dùng.
2. **Reranker (`model/bge-reranker-v2-m3`):**
   * Chấm điểm tương đồng ngữ nghĩa cấp độ Cross-Encoder cho danh sách kết quả từ Qdrant & BM25 trước khi chuyển sang Đồ thị.
3. **LLM (`Ollama Qwen`):**
   * Mặc định sử dụng `qwen2.5:3b` (hoặc chuyển sang `qwen3.5:9b` trong menu Cài đặt trên giao diện Web).
   * Đảm bảo câu trả lời chuẩn xác, không bịa đặt, bám sát các điều luật được cung cấp trong Context.
