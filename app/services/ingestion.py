import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import Document, Article, Clause, RelationshipRecord
from app.parser.legal_parser import LegalParser
from app.parser.relation_extractor import RelationExtractor
from app.vector.qdrant_store import vector_store
from app.graph.graph_store import graph_store

logger = logging.getLogger(__name__)

class IngestionPipeline:
    """
    Pipeline đồng bộ dữ liệu vào 3 kho: SQLite -> Qdrant -> Graph.
    Đảm bảo Idempotent: Có thể chạy lại nhiều lần mà không nhân bản hay làm lệch dữ liệu.
    """
    
    @classmethod
    def ingest_document(
        cls, 
        db: Session, 
        raw_text: str, 
        doc_symbol_override: Optional[str] = None,
        domain_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Nạp một văn bản quy phạm pháp luật:
        1. Parse cấu trúc
        2. Lưu SQLite
        3. Index Qdrant
        4. Cập nhật Graph
        """
        parsed = LegalParser.parse_document(raw_text, doc_symbol_override)
        meta = parsed["metadata"]
        if domain_override:
            meta["domain"] = domain_override

        doc_id = meta["doc_id"]
        if doc_id == "DOC_UNKNOWN" or not doc_id:
            import uuid
            rand_code = uuid.uuid4().hex[:8].upper()
            doc_id = f"DOC_{rand_code}"
            meta["doc_id"] = doc_id
            if meta["doc_symbol"] == "Chưa rõ số hiệu":
                meta["doc_symbol"] = f"VB-{rand_code}"
            # Cập nhật lại doc_id cho các articles
            for a in parsed["articles"]:
                a["doc_id"] = doc_id
                a["article_id"] = a["article_id"].replace("DOC_UNKNOWN", doc_id)
                for cl in a["clauses"]:
                    cl["article_id"] = a["article_id"]
                    cl["clause_id"] = cl["clause_id"].replace("DOC_UNKNOWN", doc_id)
        logger.info(f"Đang xử lý văn bản: {meta['doc_symbol']} (ID: {doc_id})")

        # 1. Trích xuất quan hệ
        guide_rels = RelationExtractor.extract_guides_relations(doc_id, raw_text)
        ref_rels = RelationExtractor.extract_article_references(doc_id, parsed["articles"])
        amend_rels = RelationExtractor.extract_amendment_relations(doc_id, parsed)
        all_rels = guide_rels + ref_rels + amend_rels

        # 2. Lưu vào SQLite (Source of Truth)
        # Xóa triệt để các điều, khoản, văn bản và quan hệ cũ nếu có (Idempotent update)
        db.query(Clause).filter(Clause.clause_id.like(f"{doc_id}_%")).delete(synchronize_session=False)
        db.query(Article).filter(Article.doc_id == doc_id).delete(synchronize_session=False)
        db.query(RelationshipRecord).filter(
            (RelationshipRecord.source_id == doc_id) | 
            (RelationshipRecord.source_id.like(f"{doc_id}_%")) |
            (RelationshipRecord.target_id == doc_id) |
            (RelationshipRecord.target_id.like(f"{doc_id}_%"))
        ).delete(synchronize_session=False)
        
        existing_doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if existing_doc:
            db.delete(existing_doc)
        db.flush()

        # Tạo mới Document
        db_doc = Document(
            doc_id=doc_id,
            doc_symbol=meta["doc_symbol"],
            title=meta["title"],
            doc_type=meta["doc_type"],
            domain=meta["domain"],
            issue_date=meta["issue_date"],
            effective_date=meta["effective_date"],
            status="active",
            full_text=raw_text,
            sync_status="PENDING"
        )
        db.add(db_doc)
        db.flush()

        # Tạo mới Articles & Clauses (với deduplication bảo vệ 2 lớp)
        seen_art_ids = set()
        for art in parsed["articles"]:
            art_id = art["article_id"]
            if art_id in seen_art_ids:
                continue
            seen_art_ids.add(art_id)

            db_art = Article(
                article_id=art_id,
                doc_id=doc_id,
                chapter_title=art["chapter_title"],
                article_number=art["article_number"],
                title=art["title"],
                content=art["content"],
                status=art["status"],
                effective_date=art["effective_date"]
            )
            db.add(db_art)
            
            seen_clause_ids = set()
            for cl in art["clauses"]:
                cl_id = cl["clause_id"]
                if cl_id in seen_clause_ids:
                    continue
                seen_clause_ids.add(cl_id)

                db_clause = Clause(
                    clause_id=cl_id,
                    article_id=art_id,
                    clause_number=cl["clause_number"],
                    content=cl["content"]
                )
                db.add(db_clause)

        # Lưu quan hệ vào bảng RelationshipRecord
        for rel in all_rels:
            db_rel = RelationshipRecord(
                source_id=rel["source_id"],
                target_id=rel["target_id"],
                rel_type=rel["rel_type"],
                details=rel["details"]
            )
            db.add(db_rel)

        db.commit()

        # 3. Nạp vào Qdrant (Hybrid Search Index)
        chunks = LegalParser.generate_qdrant_chunks(parsed)
        vector_store.upsert_chunks(chunks)

        # 4. Nạp vào Graph Store (NetworkX Engine) & Làm mới chỉ mục BM25
        graph_store.reload_from_db(db)
        vector_store.reload_bm25_from_db(db)

        # 5. Đánh dấu đã đồng bộ xong
        db_doc.sync_status = "SYNCED"
        db.commit()

        return {
            "status": "success",
            "doc_id": doc_id,
            "doc_symbol": meta["doc_symbol"],
            "title": meta["title"],
            "articles_count": len(parsed["articles"]),
            "chunks_count": len(chunks),
            "relationships_count": len(all_rels),
            "warnings": parsed["validation_warnings"]
        }
