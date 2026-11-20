import uvicorn
from app.config import settings

if __name__ == "__main__":
    print(f"================================================================")
    print(f"🚀 Khởi động Hệ Thống Trợ Lý Pháp Luật Việt Nam (Zero Docker)")
    print(f"📍 Database SQLite : {settings.SQLITE_PATH}")
    print(f"📍 Qdrant Local    : {settings.QDRANT_PATH}")
    print(f"📍 Giao diện Web   : http://{settings.HOST}:{settings.PORT}")
    print(f"================================================================")
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=False)
