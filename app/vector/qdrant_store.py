import hashlib
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, FilterSelector
from rank_bm25 import BM25Okapi
from app.config import settings
from app.vector.model_engine import EmbeddingEngine, RerankerEngine

class LocalQdrantStore:
    """
    Quản lý Vector Index trên Qdrant Local + Model cục bộ:
    1. Dense Embedding: multilingual-e5-small (384-dim)
    2. Sparse Search: BM25 Lexical
    3. Reranker: bge-reranker-v2-m3
    """
    
    COLLECTION_NAME = "legal_articles"
    
    def __init__(self):
        # Tự động dọn dẹp file .lock cũ nếu có
        lock_file = settings.QDRANT_PATH / ".lock"
        if lock_file.exists():
            try:
                lock_file.unlink()
            except Exception:
                pass
                
        # Khởi tạo Qdrant ở chế độ local file
        self.client = QdrantClient(path=str(settings.QDRANT_PATH))
        self.embedding_engine = EmbeddingEngine(settings.EMBEDDING_MODEL_PATH)
        self.reranker_engine = RerankerEngine(settings.RERANKER_MODEL_PATH)
        
        self._ensure_collection()
        self.bm25_corpus = []
        self.bm25_metadata = []
        self.bm25_model = None

    def _ensure_collection(self):
        """Tạo collection với kích thước vector 384 dim phù hợp multilingual-e5-small."""
        collections = [c.name for c in self.client.get_collections().collections]
        if self.COLLECTION_NAME in collections:
            # Kiểm tra xem kích thước vector cũ có khớp 384 không
            coll_info = self.client.get_collection(self.COLLECTION_NAME)
            current_dim = coll_info.config.params.vectors.size
            if current_dim != settings.VECTOR_DIM:
                self.client.delete_collection(self.COLLECTION_NAME)
                self.client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(size=settings.VECTOR_DIM, distance=Distance.COSINE)
                )
        else:
            self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(size=settings.VECTOR_DIM, distance=Distance.COSINE)
            )

    def upsert_chunks(self, chunks: List[Dict[str, Any]]):
        """
        Embed các chunk bằng multilingual-e5-small và nạp vào Qdrant + cập nhật BM25.
        """
        if not chunks:
            return
            
        texts_to_embed = [ch["chunk_text"] for ch in chunks]
        dense_vectors = self.embedding_engine.embed_passages(texts_to_embed)
        
        points = []
        for i, ch in enumerate(chunks):
            point_id = int(hashlib.sha256(f"{ch['article_id']}_{ch.get('clause_id')}_{ch['chunk_text']}".encode()).hexdigest()[:15], 16)
            vec = dense_vectors[i]
            
            points.append(PointStruct(
                id=point_id,
                vector=vec,
                payload={
                    "article_id": ch["article_id"],
                    "doc_id": ch["doc_id"],
                    "clause_id": ch.get("clause_id"),
                    "clause_number": ch.get("clause_number"),
                    "domain": ch.get("domain", "chung"),
                    "status": ch.get("status", "active"),
                    "effective_date": ch.get("effective_date", ""),
                    "chunk_text": ch["chunk_text"]
                }
            ))
            
        self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=points
        )
        
        # Cập nhật BM25 index
        self._build_bm25_index(chunks)

    def delete_document(self, doc_id: str):
        """Xóa toàn bộ vector và chỉ mục BM25 của một văn bản."""
        try:
            self.client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=FilterSelector(
                    filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
                )
            )
        except Exception:
            pass
            
        # Dọn dẹp BM25
        new_corpus = []
        new_meta = []
        for c, m in zip(self.bm25_corpus, self.bm25_metadata):
            if m.get("doc_id") != doc_id:
                new_corpus.append(c)
                new_meta.append(m)
        self.bm25_corpus = new_corpus
        self.bm25_metadata = new_meta
        self.bm25_model = BM25Okapi(self.bm25_corpus) if self.bm25_corpus else None

    def _build_bm25_index(self, chunks: List[Dict[str, Any]]):
        """Xây dựng hoặc cập nhật bộ chỉ mục BM25 cho tìm kiếm từ khóa chính xác."""
        for ch in chunks:
            self.bm25_corpus.append(ch["chunk_text"].lower().split())
            self.bm25_metadata.append(ch)
        if self.bm25_corpus:
            self.bm25_model = BM25Okapi(self.bm25_corpus)

    def reload_bm25_from_db(self, db):
        """
        Khởi tạo và tải lại toàn bộ chỉ mục BM25 từ tất cả Điều luật active trong SQLite.
        Đảm bảo BM25 luôn sẵn sàng hoạt động ngay sau khi khởi động server hoặc ingest văn bản mới.
        """
        try:
            from app.db.models import Article, Document
            articles = db.query(Article).filter(Article.status == "active").all()
            if not articles:
                self.bm25_corpus = []
                self.bm25_metadata = []
                self.bm25_model = None
                return

            docs_map = {d.doc_id: d for d in db.query(Document).all()}
            new_corpus = []
            new_metadata = []

            for art in articles:
                doc = docs_map.get(art.doc_id)
                doc_symbol = doc.doc_symbol if doc else art.doc_id
                domain = doc.domain if doc else "chung"
                eff_date = art.effective_date or (doc.effective_date if doc else "Hiện hành")

                header_prefix = f"[{doc_symbol} | Hiệu lực: {eff_date} | {art.chapter_title} | Điều {art.article_number}: {art.title}]"
                chunk_text = f"{header_prefix}\n{art.content}"

                meta = {
                    "article_id": art.article_id,
                    "doc_id": art.doc_id,
                    "clause_id": None,
                    "clause_number": None,
                    "domain": domain,
                    "status": art.status,
                    "effective_date": eff_date,
                    "chunk_text": chunk_text
                }
                new_corpus.append(chunk_text.lower().split())
                new_metadata.append(meta)

            self.bm25_corpus = new_corpus
            self.bm25_metadata = new_metadata
            if self.bm25_corpus:
                self.bm25_model = BM25Okapi(self.bm25_corpus)
                print(f"✅ Đã tải lại chỉ mục BM25 với {len(self.bm25_corpus)} điều luật active.")
        except Exception as e:
            print(f"⚠️ Cảnh báo tải BM25 từ SQLite: {e}")

    def hybrid_search(self, query: str, domain: Optional[str] = None, status: str = "active", top_k: int = 6) -> List[Dict[str, Any]]:
        """
        Tìm kiếm lai kết hợp:
        1. Dense Vector (multilingual-e5-small) với pool ứng viên mở rộng (top 36-50)
        2. Sparse BM25 với pool ứng viên mở rộng (top 36-50)
        3. Hard Filter status == 'active'
        4. Cross-Encoder Reranker (bge-reranker-v2-m3) chấm điểm trực tiếp từng chunk
        5. Gom điểm max theo từng Article ID để không bao giờ bỏ sót Điều luật phù hợp.
        """
        query_vec = self.embedding_engine.embed_query(query)
        
        # 1. Bộ lọc metadata cứng trên Qdrant
        must_filters = [
            FieldCondition(key="status", match=MatchValue(value=status))
        ]
        if domain:
            must_filters.append(FieldCondition(key="domain", match=MatchValue(value=domain)))
            
        qdrant_filter = Filter(must=must_filters)
        
        # Mở rộng số lượng ứng viên vòng 1 lên 18-24 điểm để Cross-Encoder chấm điểm toàn diện và nhanh trên CPU
        candidate_pool_size = max(top_k * 3, 18)

        # 2. Dense search trên Qdrant
        search_res = self.client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=query_vec,
            query_filter=qdrant_filter,
            limit=candidate_pool_size
        )
        
        points = search_res.points if hasattr(search_res, "points") else search_res
        
        # Thu thập các chunk ứng viên từ Dense search
        candidate_chunks = []
        seen_chunk_signatures = set()

        for hit in points:
            if not hit.payload:
                continue
            p = hit.payload
            sig = (p.get("article_id"), p.get("clause_id"), p.get("chunk_text", "")[:60])
            if sig not in seen_chunk_signatures:
                seen_chunk_signatures.add(sig)
                candidate_chunks.append(p)
        
        # 3. BM25 keyword score (Sparse search)
        if self.bm25_model:
            tokenized_query = query.lower().split()
            doc_scores = self.bm25_model.get_scores(tokenized_query)
            top_bm25_indices = sorted(range(len(doc_scores)), key=lambda i: doc_scores[i], reverse=True)[:candidate_pool_size]
            for idx in top_bm25_indices:
                if doc_scores[idx] > 0:
                    meta = self.bm25_metadata[idx]
                    if meta.get("status") == status:
                        sig = (meta.get("article_id"), meta.get("clause_id"), meta.get("chunk_text", "")[:60])
                        if sig not in seen_chunk_signatures:
                            seen_chunk_signatures.add(sig)
                            candidate_chunks.append(meta)

        if not candidate_chunks:
            return []

        # 4. Reranker: Dùng bge-reranker-v2-m3 chấm điểm lại toàn bộ candidate chunks
        pairs = [(query, ch["chunk_text"]) for ch in candidate_chunks]
        rerank_scores = self.reranker_engine.compute_scores(pairs)
        
        # Gom nhóm điểm cao nhất cho từng Article ID
        # (Nếu một điều luật có nhiều khoản/chunk thì lấy điểm của khoản khớp nhất)
        article_best = {}
        for i, ch in enumerate(candidate_chunks):
            aid = ch["article_id"]
            score = float(rerank_scores[i])
            if aid not in article_best or score > article_best[aid]["score"]:
                article_best[aid] = {
                    "article_id": aid,
                    "score": score,
                    "payload": ch
                }
        
        # Ngưỡng tin cậy của Reranker (loại bỏ hoàn toàn các câu hỏi không liên quan,
        # giữ lại các điều luật có liên hệ nghiệp vụ)
        RELEVANCE_THRESHOLD = 0.05
        
        ranked_results = [
            item for item in article_best.values()
            if item["score"] >= RELEVANCE_THRESHOLD
        ]
        
        ranked_results.sort(key=lambda x: x["score"], reverse=True)
        return ranked_results[:top_k]

# Global singleton instance
vector_store = LocalQdrantStore()
