import redis
from rq import Queue, Retry

from . import config

redis_conn = redis.Redis.from_url(config.REDIS_URL)
ingest_queue = Queue("ingest", connection=redis_conn)


def enqueue_ingest(document_id: int):
    # Exponential-ish backoff: retry after 10s, 30s, 90s. After that the job lands in the failed registry.
    return ingest_queue.enqueue(
        "app.tasks.process_document", document_id,
        retry=Retry(max=3, interval=[10, 30, 90]), job_timeout=600, failure_ttl=7 * 24 * 3600,
    )
