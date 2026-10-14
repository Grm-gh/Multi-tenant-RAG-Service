"""Retrieval: vector, keyword, hybrid (RRF) and hybrid + cross-encoder rerank."""
import re
import time

from .embeddings import embed_query, rerank
from .fusion import rrf

MODES = ("vector", "keyword", "hybrid", "hybrid_rerank")


def vector_search(conn, user_id: int, qvec, k: int) -> list[dict]:
    return conn.execute(
        """SELECT id, document_id, chunk_index, content
           FROM chunks WHERE user_id = %s
           ORDER BY embedding <=> %s LIMIT %s""",
        (user_id, qvec, k),
    ).fetchall()


def to_or_query(question: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9]+", question) if len(w) > 2]
    return " | ".join(dict.fromkeys(w.lower() for w in words))  # de-duplicated OR query


def keyword_search(conn, user_id: int, question: str, k: int) -> list[dict]:
    tsq = to_or_query(question)
    if not tsq:
        return []
    return conn.execute(
        """SELECT id, document_id, chunk_index, content
           FROM chunks, to_tsquery('english', %s) q
           WHERE user_id = %s AND tsv @@ q
           ORDER BY ts_rank_cd(tsv, q) DESC LIMIT %s""",
        (tsq, user_id, k),
    ).fetchall()


def retrieve(conn, user_id: int, question: str, mode: str = "hybrid_rerank",
             top_k: int = 5, candidates: int = 20) -> tuple[list[dict], dict]:
    """Returns (chunks best-first, timings_ms)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    t0 = time.perf_counter()
    timings = {"retrieval_ms": 0.0, "rerank_ms": 0.0}

    if mode == "vector":
        results = vector_search(conn, user_id, embed_query(question), top_k)
    elif mode == "keyword":
        results = keyword_search(conn, user_id, question, top_k)
    else:
        vec = vector_search(conn, user_id, embed_query(question), candidates)
        kw = keyword_search(conn, user_id, question, candidates)
        by_id = {c["id"]: c for c in vec + kw}
        fused = rrf([[c["id"] for c in vec], [c["id"] for c in kw]])
        ordered = [by_id[i] for i, _ in fused]
        if mode == "hybrid":
            results = ordered[:top_k]
        else:
            timings["retrieval_ms"] = (time.perf_counter() - t0) * 1000
            t1 = time.perf_counter()
            shortlist = ordered[:candidates]
            scores = rerank(question, [c["content"] for c in shortlist])
            results = [c for c, _ in sorted(zip(shortlist, scores), key=lambda p: p[1], reverse=True)][:top_k]
            timings["rerank_ms"] = (time.perf_counter() - t1) * 1000
            return results, timings
    timings["retrieval_ms"] = (time.perf_counter() - t0) * 1000
    return results, timings
