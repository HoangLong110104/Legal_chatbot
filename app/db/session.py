from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.db.models import Base

# SQLite connection URL
DATABASE_URL = f"sqlite:///{settings.SQLITE_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}, # Necessary for SQLite with multi-threaded FastAPI
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Tạo toàn bộ bảng trong SQLite nếu chưa tồn tại."""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Dependency cung cấp db session cho FastAPI endpoints."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
