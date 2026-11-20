from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"
    
    doc_id = Column(String(100), primary_key=True) # e.g. "168_2024_NDCP"
    doc_symbol = Column(String(100), nullable=False) # e.g. "168/2024/NĐ-CP"
    title = Column(String(500), nullable=False)
    doc_type = Column(String(50), nullable=True) # "Nghị định", "Luật", "Thông tư"
    domain = Column(String(50), default="chung") # "giao_thong", "lao_dong", "dan_su"
    issue_date = Column(String(20), nullable=True)
    effective_date = Column(String(20), nullable=True)
    status = Column(String(20), default="active") # "active", "amended", "expired"
    full_text = Column(Text, nullable=True)
    sync_status = Column(String(20), default="PENDING") # "PENDING", "SYNCED", "ERROR"
    created_at = Column(DateTime, default=datetime.utcnow)
    
    articles = relationship("Article", back_populates="document", cascade="all, delete-orphan")

class Article(Base):
    __tablename__ = "articles"
    
    article_id = Column(String(150), primary_key=True) # e.g. "168_2024_NDCP_DIEU_7"
    doc_id = Column(String(100), ForeignKey("documents.doc_id"), nullable=False, index=True)
    chapter_title = Column(String(255), nullable=True)
    article_number = Column(Integer, nullable=False)
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=False) # Toàn văn Điều luật (Parent Document)
    status = Column(String(20), default="active", index=True) # "active", "amended", "expired"
    effective_date = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    document = relationship("Document", back_populates="articles")
    clauses = relationship("Clause", back_populates="article", cascade="all, delete-orphan")

class Clause(Base):
    __tablename__ = "clauses"
    
    clause_id = Column(String(180), primary_key=True) # e.g. "168_2024_NDCP_DIEU_7_KHOAN_2"
    article_id = Column(String(150), ForeignKey("articles.article_id"), nullable=False, index=True)
    clause_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    
    article = relationship("Article", back_populates="clauses")

class RelationshipRecord(Base):
    __tablename__ = "relationships"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(150), nullable=False, index=True) # doc_id or article_id
    target_id = Column(String(150), nullable=False, index=True) # doc_id or article_id
    rel_type = Column(String(50), nullable=False, index=True) # "REFERENCES", "AMENDS", "REPLACES", "GUIDES"
    details = Column(Text, nullable=True) # JSON or note e.g. effective_date, clause_ref
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    
    session_id = Column(String(100), primary_key=True)
    title = Column(String(255), nullable=False, default="Đoạn chat mới")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChatHistory(Base):
    __tablename__ = "chat_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, index=True)
    role = Column(String(20), nullable=False) # "user", "assistant"
    content = Column(Text, nullable=False)
    citations = Column(Text, nullable=True) # JSON format
    created_at = Column(DateTime, default=datetime.utcnow)
