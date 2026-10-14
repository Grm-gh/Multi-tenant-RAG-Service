"""Embeddings + reranker behind small interfaces. Models load lazily (first use), once per process."""
import hashlib
import re
import numpy as np

from . import config

_embedder = None
_reranker = None
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge convention for queries


def _hash_embed(texts: list[str]) -> np.ndarray:
    """Deterministic bag-of-words hashing embedder. NOT semantic quality: for tests/CI only."""
    out = np.zeros((len(texts), config.EMBED_DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        for w in re.findall(r"[a-z0-9]+", t.lower()):
            h = int(hashlib.md5(w.encode()).hexdigest(), 16)
            out[i, h % config.EMBED_DIM] += 1.0 if (h >> 8) % 2 else -1.0
        n = np.linalg.norm(out[i])
        if n:
            out[i] /= n
    return out


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(config.EMBED_MODEL)
    return _embedder


def embed_documents(texts: list[str]) -> np.ndarray:
    if config.EMBEDDING_BACKEND == "hash":
        return _hash_embed(texts)
    return _get_embedder().encode(texts, batch_size=32, normalize_embeddings=True).astype(np.float32)


def embed_query(text: str) -> np.ndarray:
    if config.EMBEDDING_BACKEND == "hash":
        return _hash_embed([text])[0]
    return _get_embedder().encode([QUERY_PREFIX + text], normalize_embeddings=True)[0].astype(np.float32)


def rerank(question: str, passages: list[str]) -> list[float]:
    """Cross-encoder scores (higher = more relevant). The cross-encoder reads question+passage together."""
    if config.RERANK_BACKEND == "none":
        return [0.0] * len(passages)
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder(config.RERANK_MODEL)
    return [float(s) for s in _reranker.predict([(question, p) for p in passages])]
