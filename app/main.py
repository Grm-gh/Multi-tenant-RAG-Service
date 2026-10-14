import json
import os
import time
from contextlib import asynccontextmanager

import psycopg
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import auth, cache, config, db, llm
from .ingest import sha256_bytes
from .queue import enqueue_ingest, ingest_queue
from .ratelimit import rate_limited_user
from .search import MODES, retrieve
from .storage import path_for

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".txt", ".md", ".docx"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.get_pool()
    yield
    db.close_pool()


app = FastAPI(title="RAG Service", version="1.0", lifespan=lifespan)


# ---------- auth ----------
class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=8, max_length=200)


@app.post("/auth/register", status_code=201)
def register(body: Credentials):
    try:
        with db.get_pool().connection() as conn:
            row = conn.execute("INSERT INTO users (email, password_hash) VALUES (%s,%s) RETURNING id",
                               (body.email.lower().strip(), auth.hash_password(body.password))).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "email already registered")
    return {"token": auth.make_token(row["id"])}


@app.post("/auth/login")
def login(body: Credentials):
    with db.get_pool().connection() as conn:
        row = conn.execute("SELECT id, password_hash FROM users WHERE email=%s",
                           (body.email.lower().strip(),)).fetchone()
    if row is None or not auth.verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "invalid credentials")
    return {"token": auth.make_token(row["id"])}


# ---------- documents ----------
@app.post("/documents", status_code=202)
async def upload_document(file: UploadFile = File(...), user=Depends(auth.current_user)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, f"unsupported file type; allowed: {sorted(ALLOWED_EXT)}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large (20 MB max)")
    digest = sha256_bytes(data)
    with db.get_pool().connection() as conn:
        row = conn.execute(
            """INSERT INTO documents (user_id, filename, content_hash) VALUES (%s,%s,%s)
               ON CONFLICT (user_id, content_hash) DO NOTHING RETURNING id""",
            (user["id"], file.filename, digest)).fetchone()
        if row is None:  # same file uploaded before -> idempotent: return the existing document
            existing = conn.execute("SELECT id, status FROM documents WHERE user_id=%s AND content_hash=%s",
                                    (user["id"], digest)).fetchone()
            return {"id": existing["id"], "status": existing["status"], "duplicate": True}
        doc_id = row["id"]
    with open(path_for(doc_id, file.filename), "wb") as f:
        f.write(data)
    enqueue_ingest(doc_id)
    return {"id": doc_id, "status": "pending", "duplicate": False}


@app.get("/documents")
def list_documents(user=Depends(auth.current_user)):
    with db.get_pool().connection() as conn:
        return conn.execute("SELECT id, filename, status, error, chunk_count, created_at FROM documents "
                            "WHERE user_id=%s ORDER BY id DESC", (user["id"],)).fetchall()


@app.get("/documents/{doc_id}")
def get_document(doc_id: int, user=Depends(auth.current_user)):
    with db.get_pool().connection() as conn:
        row = conn.execute("SELECT id, filename, status, error, chunk_count, created_at FROM documents "
                           "WHERE id=%s AND user_id=%s", (doc_id, user["id"])).fetchone()
    if row is None:
        raise HTTPException(404, "not found")
    return row


@app.post("/documents/{doc_id}/retry", status_code=202)
def retry_document(doc_id: int, user=Depends(auth.current_user)):
    with db.get_pool().connection() as conn:
        row = conn.execute("UPDATE documents SET status='pending', error=NULL WHERE id=%s AND user_id=%s "
                           "AND status='failed' RETURNING id", (doc_id, user["id"])).fetchone()
    if row is None:
        raise HTTPException(409, "only failed documents of yours can be retried")
    enqueue_ingest(doc_id)
    return {"id": doc_id, "status": "pending"}


@app.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, user=Depends(auth.current_user)):
    with db.get_pool().connection() as conn:
        row = conn.execute("DELETE FROM documents WHERE id=%s AND user_id=%s RETURNING filename",
                           (doc_id, user["id"])).fetchone()
    if row is None:
        raise HTTPException(404, "not found")
    try:
        os.remove(path_for(doc_id, row["filename"]))
    except FileNotFoundError:
        pass


# ---------- query ----------
class QueryIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    mode: str = "hybrid_rerank"
    top_k: int = Field(5, ge=1, le=20)
    generate: bool = True  # False = retrieval only (used by eval + load tests, costs no LLM tokens)


def _sources(chunks: list[dict]) -> list[dict]:
    return [{"ref": i, "chunk_id": c["id"], "document_id": c["document_id"],
             "chunk_index": c["chunk_index"], "text": c["content"][:500]}
            for i, c in enumerate(chunks, start=1)]


def _log(user_id: int, body: QueryIn, cached: bool, t: dict, total_ms: float, tok_in=0, tok_out=0) -> None:
    with db.get_pool().connection() as conn:
        conn.execute(
            """INSERT INTO query_log (user_id, question, mode, cached, retrieval_ms, rerank_ms, llm_ms,
                                      total_ms, tokens_in, tokens_out) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (user_id, body.question, body.mode, cached, t.get("retrieval_ms"), t.get("rerank_ms"),
             t.get("llm_ms"), total_ms, tok_in, tok_out))


def _check_mode(body: QueryIn) -> None:
    if body.mode not in MODES:
        raise HTTPException(422, f"mode must be one of {list(MODES)}")


def _lookup(user_id: int, body: QueryIn):
    """Return (cache_key, cached_value_or_None)."""
    with db.get_pool().connection() as conn:
        key = cache.make_key(user_id, cache.corpus_version(conn, user_id), body.question, body.mode, body.top_k)
    return key, cache.get(key)


def _retrieve(user_id: int, body: QueryIn):
    with db.get_pool().connection() as conn:
        return retrieve(conn, user_id, body.question, body.mode, body.top_k)


@app.post("/query")
def query(body: QueryIn, user=Depends(rate_limited_user)):
    _check_mode(body)
    t0 = time.perf_counter()
    if not body.generate:
        chunks, timings = _retrieve(user["id"], body)
        _log(user["id"], body, False, timings, (time.perf_counter() - t0) * 1000)
        return {"sources": _sources(chunks), "timings_ms": timings}
    key, hit = _lookup(user["id"], body)
    if hit:
        _log(user["id"], body, True, {}, (time.perf_counter() - t0) * 1000)
        return {**hit, "cached": True}
    chunks, timings = _retrieve(user["id"], body)
    t1 = time.perf_counter()
    answer, usage = "", (0, 0)
    for kind, val in llm.stream_answer(body.question, chunks):
        if kind == "token":
            answer += val
        else:
            usage = val
    timings["llm_ms"] = (time.perf_counter() - t1) * 1000
    result = {"answer": answer, "sources": _sources(chunks), "timings_ms": timings, "usage": usage}
    cache.put(key, result)
    _log(user["id"], body, False, timings, (time.perf_counter() - t0) * 1000, *usage)
    return {**result, "cached": False}


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/query/stream")
def query_stream(body: QueryIn, user=Depends(rate_limited_user)):
    """Server-Sent Events: `sources` first (so the UI can show citations), then `token`s, then `done`."""
    _check_mode(body)
    user_id = user["id"]

    def events():
        t0 = time.perf_counter()
        key, hit = _lookup(user_id, body)
        if hit:
            yield _sse("sources", hit["sources"])
            yield _sse("token", hit["answer"])
            yield _sse("done", {"cached": True})
            _log(user_id, body, True, {}, (time.perf_counter() - t0) * 1000)
            return
        chunks, timings = _retrieve(user_id, body)
        yield _sse("sources", _sources(chunks))
        t1 = time.perf_counter()
        answer, usage = "", (0, 0)
        for kind, val in llm.stream_answer(body.question, chunks):
            if kind == "token":
                answer += val
                yield _sse("token", val)
            else:
                usage = val
        timings["llm_ms"] = (time.perf_counter() - t1) * 1000
        cache.put(key, {"answer": answer, "sources": _sources(chunks), "timings_ms": timings, "usage": usage})
        _log(user_id, body, False, timings, (time.perf_counter() - t0) * 1000, *usage)
        yield _sse("done", {"cached": False, "timings_ms": timings, "usage": usage})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------- ops ----------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics(user=Depends(auth.current_user)):
    """Latency percentiles per stage, cache hit rate, token usage and queue depth (last 1000 queries)."""
    with db.get_pool().connection() as conn:
        row = conn.execute(
            """WITH recent AS (SELECT * FROM query_log ORDER BY id DESC LIMIT 1000)
               SELECT COUNT(*) AS queries,
                      COALESCE(AVG(cached::int),0) AS cache_hit_rate,
                      percentile_cont(0.5)  WITHIN GROUP (ORDER BY total_ms) AS total_p50_ms,
                      percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms) AS total_p95_ms,
                      percentile_cont(0.95) WITHIN GROUP (ORDER BY retrieval_ms) AS retrieval_p95_ms,
                      percentile_cont(0.95) WITHIN GROUP (ORDER BY rerank_ms) AS rerank_p95_ms,
                      percentile_cont(0.95) WITHIN GROUP (ORDER BY llm_ms) AS llm_p95_ms,
                      COALESCE(SUM(tokens_in),0) AS tokens_in, COALESCE(SUM(tokens_out),0) AS tokens_out
               FROM recent""").fetchone()
    row["queue_depth"] = ingest_queue.count
    row["dead_letter_jobs"] = ingest_queue.failed_job_registry.count
    return row
