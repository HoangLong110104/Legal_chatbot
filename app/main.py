import os
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Depends, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.config import settings
from app.db.session import init_db, get_db
from app.db.models import Document, Article, RelationshipRecord, ChatSession, ChatHistory
from app.agent.workflow import AgenticWorkflow
from app.services.seed_data import seed_sample_laws
from app.services.ingestion import IngestionPipeline
from app.services.document_reader import extract_text_from_file
from app.vector.qdrant_store import vector_store
from app.graph.graph_store import graph_store

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Hệ thống hỏi đáp pháp luật Việt Nam (Agentic Graph RAG - Zero Docker)"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static folder
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.on_event("startup")
def on_startup():
    """Khởi tạo SQLite DB, Graph Store, BM25 Index và tự động nạp dữ liệu mẫu nếu chưa có."""
    init_db()
    
    # Nạp đồ thị và BM25 vào bộ nhớ
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        # Nếu chưa có văn bản nào trong DB, tự động seed mẫu
        doc_count = db.query(Document).count()
        if doc_count == 0:
            seed_sample_laws(db)
        graph_store.reload_from_db(db)
        vector_store.reload_bm25_from_db(db)
    finally:
        db.close()

@app.get("/")
def get_index():
    """Phục vụ giao diện Chatbot với no-cache để luôn cập nhật script mới nhất."""
    response = FileResponse(STATIC_DIR / "index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# =====================================================================
# CHAT SESSIONS & HISTORY API
# =====================================================================

class CreateSessionRequest(BaseModel):
    title: Optional[str] = "Đoạn chat mới"

@app.get("/api/sessions")
def list_sessions(db: Session = Depends(get_db)):
    """Lấy danh sách các phiên trò chuyện, sắp xếp theo thời gian mới nhất."""
    sessions = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()
    results = []
    for s in sessions:
        msg_count = db.query(ChatHistory).filter(ChatHistory.session_id == s.session_id).count()
        results.append({
            "session_id": s.session_id,
            "title": s.title,
            "message_count": msg_count,
            "created_at": s.created_at.strftime("%H:%M %d/%m/%Y") if s.created_at else "",
            "updated_at": s.updated_at.strftime("%H:%M %d/%m/%Y") if s.updated_at else ""
        })
    return results

@app.post("/api/sessions")
def create_session(req: CreateSessionRequest = Body(default=None), db: Session = Depends(get_db)):
    """Tạo một phiên hội thoại mới."""
    new_id = str(uuid.uuid4())
    title = (req.title if req and req.title else "Đoạn chat mới").strip()
    session = ChatSession(
        session_id=new_id,
        title=title,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(session)
    db.commit()
    return {"session_id": new_id, "title": title}

@app.get("/api/sessions/{session_id}")
def get_session_detail(session_id: str, db: Session = Depends(get_db)):
    """Lấy toàn bộ lịch sử tin nhắn trong một phiên hội thoại."""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên trò chuyện.")
        
    messages = db.query(ChatHistory).filter(
        ChatHistory.session_id == session_id
    ).order_by(ChatHistory.created_at.asc()).all()
    
    msg_list = []
    for m in messages:
        cits = []
        if m.citations:
            try:
                cits = json.loads(m.citations)
            except Exception:
                cits = []
        msg_list.append({
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "citations": cits,
            "created_at": m.created_at.strftime("%H:%M %d/%m/%Y") if m.created_at else ""
        })
        
    return {
        "session_id": session.session_id,
        "title": session.title,
        "messages": msg_list
    }

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """Xóa một phiên hội thoại và toàn bộ tin nhắn liên quan."""
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên trò chuyện.")
        
    db.query(ChatHistory).filter(ChatHistory.session_id == session_id).delete(synchronize_session=False)
    db.delete(session)
    db.commit()
    return {"status": "success", "deleted_session_id": session_id}

# =====================================================================
# AGENTIC CHAT STREAM API
# =====================================================================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, db: Session = Depends(get_db)):
    """
    Endpoint chính xử lý hội thoại:
    Stream từng bước suy luận qua SSE và lưu trữ lịch sử vào SQLite.
    """
    session_id = req.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        
    # Đảm bảo phiên tồn tại trong DB
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raw_title = req.message.strip()
        title = (raw_title[:38] + "...") if len(raw_title) > 38 else raw_title
        session = ChatSession(
            session_id=session_id,
            title=title or "Đoạn chat mới",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(session)
        db.commit()
    else:
        # Nếu phiên mới có tiêu đề mặc định và chưa có tin nhắn, đặt theo câu hỏi đầu tiên
        if session.title == "Đoạn chat mới":
            raw_title = req.message.strip()
            session.title = (raw_title[:38] + "...") if len(raw_title) > 38 else raw_title
        session.updated_at = datetime.utcnow()
        db.commit()

    # Lưu câu hỏi người dùng vào ChatHistory
    user_msg = ChatHistory(
        session_id=session_id,
        role="user",
        content=req.message,
        created_at=datetime.utcnow()
    )
    db.add(user_msg)
    db.commit()

    workflow = AgenticWorkflow(db)

    async def event_generator():
        # Gửi thông báo session_id trước để frontend đồng bộ
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id, 'title': session.title})}\n\n"
        
        final_answer = ""
        final_citations = []
        
        async for event_str in workflow.stream_workflow(req.message):
            try:
                ev_data = json.loads(event_str)
                if ev_data.get("type") == "answer":
                    final_answer = ev_data.get("content", "")
                elif ev_data.get("type") == "citations":
                    final_citations = ev_data.get("citations", [])
            except Exception:
                pass
            yield f"data: {event_str}\n\n"

        # Khi kết thúc luồng SSE, lưu câu trả lời của trợ lý vào ChatHistory
        if final_answer:
            try:
                from app.db.session import SessionLocal
                save_db = SessionLocal()
                try:
                    assistant_msg = ChatHistory(
                        session_id=session_id,
                        role="assistant",
                        content=final_answer,
                        citations=json.dumps(final_citations, ensure_ascii=False) if final_citations else None,
                        created_at=datetime.utcnow()
                    )
                    save_db.add(assistant_msg)
                    save_db.commit()
                finally:
                    save_db.close()
            except Exception as e:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# =====================================================================
# LEGAL DOCUMENTS & KNOWLEDGE MANAGEMENT API
# =====================================================================

@app.get("/api/documents")
def list_documents(db: Session = Depends(get_db)):
    """Lấy danh sách các văn bản pháp luật hiện có trong hệ thống."""
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    results = []
    for d in docs:
        art_count = db.query(Article).filter(Article.doc_id == d.doc_id).count()
        results.append({
            "doc_id": d.doc_id,
            "doc_symbol": d.doc_symbol,
            "title": d.title,
            "doc_type": d.doc_type or "Văn bản",
            "domain": d.domain or "chung",
            "effective_date": d.effective_date or d.issue_date or "Chưa rõ",
            "status": d.status or "active",
            "sync_status": d.sync_status or "SYNCED",
            "articles_count": art_count,
            "created_at": d.created_at.strftime("%d/%m/%Y") if d.created_at else ""
        })
    return results

@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    doc_symbol: Optional[str] = Form(None),
    domain: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Tải lên file văn bản pháp luật (.txt, .pdf, .docx):
    Tự động trích xuất text, parse cấu trúc, nạp vào SQLite, Qdrant và Graph Store.
    """
    content_bytes = await file.read()
    if not content_bytes:
        raise HTTPException(status_code=400, detail="File tải lên rỗng.")
        
    try:
        raw_text = extract_text_from_file(file.filename, content_bytes)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Không thể xử lý file: {str(e)}")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Nội dung trích xuất từ file rỗng.")

    try:
        res = IngestionPipeline.ingest_document(
            db=db,
            raw_text=raw_text,
            doc_symbol_override=doc_symbol.strip() if doc_symbol else None,
            domain_override=domain.strip() if domain else None
        )
        return res
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Lỗi khi nạp và phân tích văn bản: {str(e)}")

class RawDocRequest(BaseModel):
    raw_text: str
    doc_symbol: Optional[str] = None
    domain: Optional[str] = None

@app.post("/api/documents/raw")
def ingest_raw_document(req: RawDocRequest, db: Session = Depends(get_db)):
    """Nạp văn bản pháp luật bằng cách dán trực tiếp nội dung văn bản."""
    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="Nội dung văn bản không được để trống.")
        
    try:
        res = IngestionPipeline.ingest_document(
            db=db,
            raw_text=req.raw_text,
            doc_symbol_override=req.doc_symbol.strip() if req.doc_symbol else None,
            domain_override=req.domain.strip() if req.domain else None
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi nạp văn bản: {str(e)}")

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    """
    Xóa một văn bản pháp luật khỏi toàn bộ 3 kho:
    1. Xóa trong SQLite (Document, Articles, Clauses, Relationships)
    2. Xóa các vector trong Qdrant Local
    3. Cập nhật lại NetworkX Graph Engine
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy văn bản để xóa.")

    doc_symbol = doc.doc_symbol

    # 1. Xóa trong SQLite
    # Xóa quan hệ
    db.query(RelationshipRecord).filter(
        (RelationshipRecord.source_id == doc_id) |
        (RelationshipRecord.source_id.like(f"{doc_id}_%")) |
        (RelationshipRecord.target_id == doc_id) |
        (RelationshipRecord.target_id.like(f"{doc_id}_%"))
    ).delete(synchronize_session=False)

    # Xóa document (cascade delete articles and clauses)
    db.delete(doc)
    db.commit()

    # 2. Xóa trong Qdrant Local
    vector_store.delete_document(doc_id)

    # 3. Nạp lại Graph NetworkX từ SQLite còn lại
    graph_store.reload_from_db(db)

    return {
        "status": "success",
        "message": f"Đã xóa thành công văn bản {doc_symbol} khỏi cả 3 kho dữ liệu.",
        "doc_id": doc_id
    }

# =====================================================================
# SYSTEM & STATS API
# =====================================================================

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Trả về số liệu thống kê hệ thống 3 kho."""
    docs_cnt = db.query(Document).count()
    articles_cnt = db.query(Article).count()
    rels_cnt = db.query(RelationshipRecord).count()
    sessions_cnt = db.query(ChatSession).count()
    
    return {
        "documents_count": docs_cnt,
        "articles_count": articles_cnt,
        "relationships_count": rels_cnt,
        "sessions_count": sessions_cnt,
        "graph_nodes": len(graph_store.graph.nodes),
        "graph_edges": len(graph_store.graph.edges)
    }

@app.get("/api/article/{article_id}")
def get_article_detail(article_id: str, db: Session = Depends(get_db)):
    """Lấy toàn văn Điều luật từ SQLite (Parent Document) kèm thông tin đồ thị."""
    art = db.query(Article).filter(Article.article_id == article_id).first()
    if not art:
        raise HTTPException(status_code=404, detail="Không tìm thấy điều luật")
        
    doc = db.query(Document).filter(Document.doc_id == art.doc_id).first()
    amend_info = graph_store.get_amendment_chain(article_id)
    refs = graph_store.get_cross_references(article_id)
    
    return {
        "article_id": art.article_id,
        "doc_id": art.doc_id,
        "doc_symbol": doc.doc_symbol if doc else art.doc_id,
        "chapter_title": art.chapter_title,
        "article_number": art.article_number,
        "title": art.title,
        "content": art.content,
        "status": art.status,
        "effective_date": art.effective_date,
        "amendment_chain": amend_info,
        "references": refs
    }

@app.post("/api/seed")
def seed_data(db: Session = Depends(get_db)):
    """Nạp bộ dữ liệu luật mẫu vào hệ thống."""
    results = seed_sample_laws(db)
    return results

@app.get("/api/settings")
def get_settings():
    """Lấy thông tin cấu hình runtime."""
    return {
        "gemini_key": settings.GEMINI_API_KEY[:4] + "****" if settings.GEMINI_API_KEY else "",
        "openai_key": settings.OPENAI_API_KEY[:4] + "****" if settings.OPENAI_API_KEY else "",
        "llm_provider": settings.LLM_PROVIDER,
        "ollama_model": settings.OLLAMA_MODEL,
        "embedding_model": "multilingual-e5-small (Local)",
        "reranker_model": "bge-reranker-v2-m3 (Local)"
    }

@app.post("/api/settings")
def save_settings(data: Dict[str, str] = Body(...)):
    """Cập nhật runtime settings."""
    if "ollama_model" in data and data["ollama_model"]:
        settings.OLLAMA_MODEL = data["ollama_model"]
    if "gemini_key" in data and data["gemini_key"]:
        settings.GEMINI_API_KEY = data["gemini_key"]
    if "openai_key" in data and data["openai_key"]:
        settings.OPENAI_API_KEY = data["openai_key"]
    return {"status": "success", "ollama_model": settings.OLLAMA_MODEL}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
