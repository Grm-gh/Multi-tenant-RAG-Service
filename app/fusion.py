"""Reciprocal Rank Fusion: merge several ranked lists without normalising their scores."""


def rrf(ranked_lists: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Each list is chunk ids best-first. score(id) = sum over lists of 1 / (k + rank)."""
    scores: dict[int, float] = {}
    for ranking in ranked_lists:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
