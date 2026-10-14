"""Retrieval metrics (pure functions)."""
import re


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def hit_rank(chunk_texts: list[str], evidence: str) -> int | None:
    """1-based rank of the first chunk containing the evidence phrase, else None.

    Relevance is judged by a short evidence phrase, not a chunk id, so the same golden set works
    for every chunk size we try.
    """
    ev = norm(evidence)
    for rank, text in enumerate(chunk_texts, start=1):
        if ev in norm(text):
            return rank
    return None


def recall_at_k(ranks: list[int | None], k: int) -> float:
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks) if ranks else 0.0


def mrr(ranks: list[int | None]) -> float:
    return sum(1.0 / r for r in ranks if r) / len(ranks) if ranks else 0.0
