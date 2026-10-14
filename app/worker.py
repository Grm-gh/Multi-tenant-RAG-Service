"""Entry point for the ingestion worker:  python -m app.worker"""
from rq import Worker

from .queue import ingest_queue, redis_conn

if __name__ == "__main__":
    from . import db
    db.init_db()  # schema only: connections are opened per job, inside the forked child
    Worker([ingest_queue], connection=redis_conn).work()
