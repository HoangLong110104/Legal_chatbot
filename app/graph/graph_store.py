import networkx as nx
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import RelationshipRecord, Article, Document

class LocalGraphStore:
    """
    Graph Engine cục bộ dựa trên NetworkX + SQLite.
    Thực thi chính xác các logic Parameterized Cypher từ bản thiết kế mà không cần Neo4j Server.
    """
    
    def __init__(self):
        self.graph = nx.DiGraph()
        
    def reload_from_db(self, db: Session):
        """Tải toàn bộ Node và Cạnh quan hệ từ SQLite vào bộ nhớ đồ thị."""
        self.graph.clear()
        
        # 1. Nạp Nodes Documents
        docs = db.query(Document).all()
        for doc in docs:
            self.graph.add_node(
                doc.doc_id,
                node_type="Document",
                doc_symbol=doc.doc_symbol,
                title=doc.title,
                status=doc.status,
                effective_date=doc.effective_date or ""
            )
            
        # 2. Nạp Nodes Articles
        articles = db.query(Article).all()
        for art in articles:
            self.graph.add_node(
                art.article_id,
                node_type="Article",
                doc_id=art.doc_id,
                article_number=art.article_number,
                title=art.title,
                status=art.status,
                effective_date=art.effective_date or ""
            )
            # Nối cạnh CONTAINS giữa Document và Article
            self.graph.add_edge(art.doc_id, art.article_id, rel_type="CONTAINS")
            
        # 3. Nạp Edges từ bảng relationships
        records = db.query(RelationshipRecord).all()
        for r in records:
            # Nếu target node chưa có (Tham chiếu treo / Stub Node)
            if not self.graph.has_node(r.target_id):
                self.graph.add_node(
                    r.target_id,
                    node_type="Article" if "_DIEU_" in r.target_id else "Document",
                    status="active", # Giả định mặc định cho stub node
                    is_stub=True
                )
            if not self.graph.has_node(r.source_id):
                self.graph.add_node(
                    r.source_id,
                    node_type="Article" if "_DIEU_" in r.source_id else "Document",
                    status="active",
                    is_stub=True
                )
                
            self.graph.add_edge(r.source_id, r.target_id, rel_type=r.rel_type, details=r.details or "")

    def get_amendment_chain(self, article_id: str, max_depth: int = 5) -> Dict[str, Any]:
        """
        Truy vết chuỗi sửa đổi bắc cầu (AMENDS*1..5) để tìm ra phiên bản mới nhất còn hiệu lực.
        Tương đương Cypher:
        MATCH path = (latest:Article)-[:AMENDS*1..5]->(old:Article {article_id: $article_id})
        WHERE latest.status = 'active'
        """
        if not self.graph.has_node(article_id):
            return {"latest_id": article_id, "is_amended": False, "history": []}
            
        # Tìm các node trỏ tới article_id bằng cạnh AMENDS (nghĩa là node_mới -[:AMENDS]-> node_cũ)
        current = article_id
        chain = []
        depth = 0
        
        while depth < max_depth:
            # Tìm predecessor qua cạnh AMENDS
            amenders = [
                u for u, v, data in self.graph.in_edges(current, data=True)
                if data.get("rel_type") == "AMENDS"
            ]
            if not amenders:
                break
            latest_amender = amenders[0] # Lấy bản sửa đổi gần nhất
            node_data = self.graph.nodes.get(latest_amender, {})
            chain.append({
                "article_id": latest_amender,
                "status": node_data.get("status", "active"),
                "effective_date": node_data.get("effective_date", "")
            })
            current = latest_amender
            depth += 1
            
        return {
            "latest_id": current,
            "is_amended": len(chain) > 0,
            "chain": chain
        }

    def get_cross_references(self, article_id: str, max_refs: int = 8) -> List[Dict[str, Any]]:
        """
        Lấy các điều luật được tham chiếu trực tiếp (giới hạn 1-hop và max_refs còn hiệu lực).
        Tương đương Cypher:
        MATCH (a:Article {article_id: $article_id})-[:REFERENCES]->(ref:Article)
        WHERE ref.status = 'active'
        """
        if not self.graph.has_node(article_id):
            return []
            
        refs = []
        for u, v, data in self.graph.out_edges(article_id, data=True):
            if data.get("rel_type") == "REFERENCES":
                target_node = self.graph.nodes.get(v, {})
                status = target_node.get("status", "active")
                if status == "active":
                    refs.append({
                        "target_id": v,
                        "rel_type": "REFERENCES",
                        "details": data.get("details", ""),
                        "node_info": target_node
                    })
                    if len(refs) >= max_refs:
                        break
        return refs

    def get_guiding_documents(self, doc_id: str, max_guides: int = 5) -> List[Dict[str, Any]]:
        """
        Tìm các Nghị định/Thông tư hướng dẫn thi hành còn hiệu lực.
        Tương đương Cypher:
        MATCH (guide:Document)-[:GUIDES]->(base:Document {doc_id: $doc_id})
        WHERE guide.status = 'active'
        """
        if not self.graph.has_node(doc_id):
            return []
            
        guides = []
        for u, v, data in self.graph.in_edges(doc_id, data=True):
            if data.get("rel_type") == "GUIDES":
                guide_node = self.graph.nodes.get(u, {})
                if guide_node.get("status", "active") == "active":
                    guides.append({
                        "doc_id": u,
                        "title": guide_node.get("title", ""),
                        "details": data.get("details", "")
                    })
                    if len(guides) >= max_guides:
                        break
        return guides

    def get_subgraph_for_visualization(self, focus_ids: List[str]) -> Dict[str, Any]:
        """Trả về dữ liệu graph định dạng nodes & links để vẽ trên giao diện UI."""
        nodes = []
        links = []
        visited_nodes = set()
        
        for fid in focus_ids:
            if not self.graph.has_node(fid):
                continue
            if fid not in visited_nodes:
                visited_nodes.add(fid)
                n_data = self.graph.nodes[fid]
                nodes.append({
                    "id": fid,
                    "label": n_data.get("title", fid),
                    "type": n_data.get("node_type", "Article"),
                    "status": n_data.get("status", "active"),
                    "is_focus": True
                })
                
            # Duyệt các cạnh lân cận 1-hop
            for u, v, data in self.graph.edges(fid, data=True):
                rel = data.get("rel_type", "RELATED")
                links.append({"source": u, "target": v, "label": rel})
                if v not in visited_nodes:
                    visited_nodes.add(v)
                    v_data = self.graph.nodes.get(v, {})
                    nodes.append({
                        "id": v,
                        "label": v_data.get("title", v),
                        "type": v_data.get("node_type", "Article"),
                        "status": v_data.get("status", "active"),
                        "is_focus": False
                    })
                    
        return {"nodes": nodes, "links": links}

# Global singleton graph instance
graph_store = LocalGraphStore()
