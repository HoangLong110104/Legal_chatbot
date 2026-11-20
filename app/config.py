import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "model"

class Settings(BaseSettings):
    APP_NAME: str = "Hệ Thống Trợ Lý Pháp Luật Việt Nam (Agentic Graph RAG)"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Paths
    SQLITE_PATH: Path = DATA_DIR / "legal.db"
    QDRANT_PATH: Path = DATA_DIR / "qdrant_local"
    EMBEDDING_MODEL_PATH: Path = MODEL_DIR / "multilingual-e5-small"
    RERANKER_MODEL_PATH: Path = MODEL_DIR / "bge-reranker-v2-m3"
    
    # Vector DB
    VECTOR_DIM: int = 384 # multilingual-e5-small embedding dimension
    
    # Local & Serving LLM Engines (Ollama / vLLM / SGLang)
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen2.5:1.5b" # Có thể đổi sang qwen2.5:3b / qwen3.5:9b
    VLLM_BASE_URL: str = "http://127.0.0.1:8001/v1"
    VLLM_MODEL: str = str(MODEL_DIR / "Qwen2.5-1.5B-Instruct")
    SGLANG_BASE_URL: str = "http://127.0.0.1:30000/v1"
    SGLANG_MODEL: str = str(MODEL_DIR / "Qwen2.5-1.5B-Instruct")
    LLM_PROVIDER: str = "ollama" # "ollama", "vllm", "sglang", "gemini", "openai"
    
    # Cloud LLM Fallbacks (Optional)
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-2.5-flash"
    
    # RAG Settings
    TOP_K_ANCHOR: int = 6
    MAX_EXPAND_HOPS: int = 2
    MAX_REFERENCES_PER_NODE: int = 8
    
    # Server
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.QDRANT_PATH.mkdir(parents=True, exist_ok=True)
