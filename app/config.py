import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://rag:rag@localhost:5432/rag")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_TTL_SECONDS = 60 * 60 * 24
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "st")
RERANK_BACKEND = os.getenv("RERANK_BACKEND", "ce")
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
EMBED_DIM = 384
RATE_CAPACITY = float(os.getenv("RATE_CAPACITY", "20"))
RATE_REFILL_PER_SEC = float(os.getenv("RATE_REFILL_PER_SEC", "0.5"))
CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "350"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "60"))
CACHE_TTL_SECONDS = 3600
