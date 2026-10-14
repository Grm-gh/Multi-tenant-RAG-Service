"""Paragraph-aware, overlapping, word-based chunker (pure function, easy to test)."""
import re


def chunk_text(text: str, size: int = 350, overlap: int = 60) -> list[str]:
    """Split text into ~`size`-word chunks that never cut a paragraph unnecessarily.

    Consecutive chunks share `overlap` words so an answer sitting on a boundary
    still appears whole in at least one chunk.
    """
    if size <= overlap:
        raise ValueError("size must be larger than overlap")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur: list[str] = []

    def flush() -> None:
        nonlocal cur
        if cur:
            chunks.append(" ".join(cur))
            cur = cur[-overlap:] if overlap else []

    for para in paragraphs:
        words = para.split()
        # Keep a paragraph whole when it fits in a fresh chunk; otherwise start a new chunk first.
        if cur and len(cur) + len(words) > size and len(words) <= size - overlap:
            flush()
        while words:  # fill the current chunk word by word; never exceed `size`
            take = size - len(cur)
            if take <= 0:
                flush()
                continue
            cur.extend(words[:take])
            words = words[take:]
            if words:
                flush()

    # Emit the remainder unless it is nothing but the overlap carried from the previous chunk.
    if cur and (not chunks or len(cur) > overlap):
        chunks.append(" ".join(cur))
    return chunks
