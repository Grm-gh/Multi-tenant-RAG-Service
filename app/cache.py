"""Answer cache. The key includes a 'corpus version', so uploading/deleting docs invalidates old answers."""
import hashlib
import json

from . import config
from .queue import redis_conn


def corpus_version(conn, user_id: int) -> str:
    r = conn.execute("SELECT COALESCE(MAX(id),0) AS m, COUNT(*) AS n FROM documents WHERE user_id=%s AND status='ready'",
                     (user_id,)).fetchone()
    return f"{r['m']}-{r['n']}"


def make_key(user_id: int, version: str, question: str, mode: str, top_k: int) -> str:
    norm = " ".join(question.lower().split())
    return "ans:" + hashlib.sha256(f"{user_id}|{version}|{mode}|{top_k}|{norm}".encode()).hexdigest()


def get(key: str):
    raw = redis_conn.get(key)
    return json.loads(raw) if raw else None


def put(key: str, value: dict) -> None:
    redis_conn.set(key, json.dumps(value), ex=config.CACHE_TTL_SECONDS)
