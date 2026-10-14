"""Background job run by RQ workers."""
from rq import get_current_job

from . import db
from .ingest import ingest_document


def process_document(document_id: int) -> None:
    pool = db.get_pool()
    job = get_current_job()
    with pool.connection() as conn:
        row = conn.execute("SELECT user_id, filename FROM documents WHERE id=%s", (document_id,)).fetchone()
        if row is None:
            return  # deleted before the worker got to it
        conn.execute("UPDATE documents SET status='processing' WHERE id=%s", (document_id,))
    from .storage import path_for
    try:
        with pool.connection() as conn:
            ingest_document(conn, document_id, row["user_id"], path_for(document_id, row["filename"]))
    except Exception as exc:
        retries_left = getattr(job, "retries_left", None) if job else None
        final = not retries_left  # None or 0 => this was the last attempt
        with pool.connection() as conn:
            conn.execute("UPDATE documents SET status=%s, error=%s WHERE id=%s",
                         ("failed" if final else "retrying", str(exc)[:500], document_id))
        raise  # lets RQ schedule the retry (or move the job to the failed registry = dead-letter)
