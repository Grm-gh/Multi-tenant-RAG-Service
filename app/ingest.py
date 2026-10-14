"""Parse -> chunk -> embed -> store. Safe to run twice for the same document (idempotent)."""
import hashlib
import os

from . import config
from .chunking import chunk_text
from .embeddings import embed_documents


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join((page.extract_text() or "") for page in PdfReader(path).pages)
    if ext == ".docx":
        import docx
        return "\n\n".join(p.text for p in docx.Document(path).paragraphs)
    with open(path, "rb") as f:  # .txt / .md / anything text-like
        return f.read().decode("utf-8", errors="ignore")


def ingest_document(conn, document_id: int, user_id: int, path: str,
                    chunk_size: int | None = None, overlap: int | None = None) -> int:
    """Replace all chunks of this document in ONE transaction, so retries never create duplicates."""
    text = parse_file(path)
    pieces = chunk_text(text, chunk_size or config.CHUNK_WORDS, config.CHUNK_OVERLAP if overlap is None else overlap)
    if not pieces:
        raise ValueError("no extractable text in document")
    vectors = embed_documents(pieces)
    with conn.transaction():
        conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (document_id, user_id, chunk_index, content, embedding) VALUES (%s,%s,%s,%s,%s)",
                [(document_id, user_id, i, piece, vectors[i]) for i, piece in enumerate(pieces)],
            )
        conn.execute("UPDATE documents SET status='ready', error=NULL, chunk_count=%s WHERE id=%s",
                     (len(pieces), document_id))
    return len(pieces)
