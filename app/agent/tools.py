from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import Article, Document
from app.vector.qdrant_store import vector_store
from app.graph.graph_store import graph_store

class LegalAgentTools:
    """Bộ công cụ Parameterized chuẩn hóa cho Agent truy vấn 3 kho."""
    
    @staticmethod
    def search_law(query: str, domain: Optional[str] = None, status: str = "active", top_k: int = 6) -> List[Dict[str, Any]]:
        """
        Tool 1: Tìm kiếm điểm neo ngữ nghĩa + từ khóa trên Qdrant.
        Luôn ép cứng bộ lọc status == 'active'.
        """
        return vector_store.hybrid_search(query=query, domain=domain, status=status, top_k=top_k)

    @staticmethod
    def get_amendment_chain(article_id: str) -> Dict[str, Any]:
        """
        Tool 2: Truy vết đồ thị xem Điều luật này có bị sửa đổi/bãi bỏ bởi văn bản mới hơn không.
        """
        return graph_store.get_amendment_chain(article_id)

    @staticmethod
    def get_cross_references(article_id: str, max_refs: int = 8) -> List[Dict[str, Any]]:
        """
        Tool 3: Lấy các điều khoản được tham chiếu chéo trực tiếp (1-hop) còn hiệu lực.
        """
        return graph_store.get_cross_references(article_id, max_refs)

    @staticmethod
    def get_guiding_documents(doc_id: str) -> List[Dict[str, Any]]:
        """
        Tool 4: Tìm các Nghị định/Thông tư hướng dẫn thi hành còn hiệu lực.
        """
        return graph_store.get_guiding_documents(doc_id)

    @staticmethod
    def fetch_articles_content(db: Session, article_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Tool 5: Batch query SQLite lấy toàn văn các Điều luật (Parent Documents) đưa vào context của LLM.
        """
        if not article_ids:
            return []
            
        articles = db.query(Article).filter(Article.article_id.in_(article_ids)).all()
        result = []
        for a in articles:
            result.append({
                "article_id": a.article_id,
                "doc_id": a.doc_id,
                "article_number": a.article_number,
                "title": a.title,
                "chapter_title": a.chapter_title,
                "content": a.content,
                "status": a.status,
                "effective_date": a.effective_date
            })
        return result
