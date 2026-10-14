"""Postgres access. One connection pool per process; schema created idempotently at startup."""
import os
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

from . import config

_pool: ConnectionPool | None = None
_pool_pid: int | None = None


def init_db() -> None:
    """Create extension/tables. An advisory lock stops the API and the worker racing on first boot."""
    schema = open(os.path.join(os.path.dirname(__file__), "schema.sql")).read()
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(424242)")
        try:
            conn.execute(schema)
        finally:
            conn.execute("SELECT pg_advisory_unlock(424242)")


def get_pool() -> ConnectionPool:
    """Process-local pool. RQ forks a child per job; sockets inherited across fork() are corrupt to share,
    so a child that sees a different pid drops the parent's pool (without closing it) and builds its own."""
    global _pool, _pool_pid
    if _pool is not None and _pool_pid != os.getpid():
        _pool = None
    if _pool is None:
        _pool_pid = os.getpid()
        init_db()  # extension must exist before register_vector runs on new connections
        _pool = ConnectionPool(
            config.DATABASE_URL,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            configure=register_vector,
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
