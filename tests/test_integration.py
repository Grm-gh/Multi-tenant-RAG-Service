"""End-to-end test against real Postgres+pgvector and Redis.  Run with:  RUN_INTEGRATION=1 pytest tests/test_integration.py
Uses the hash embedder and no reranker/LLM so it needs no model downloads or API keys."""
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1")

ROOT = os.path.dirname(os.path.dirname(__file__))
DOC = os.path.join(ROOT, "eval/docs/nimbus_handbook.md")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ.setdefault("EMBEDDING_BACKEND", "hash")
    os.environ.setdefault("RERANK_BACKEND", "none")
    os.environ["UPLOAD_DIR"] = str(tmp_path_factory.mktemp("uploads"))
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def signup(client):
    r = client.post("/auth/register", json={"email": f"{uuid.uuid4().hex[:8]}@t.io", "password": "password123"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['token']}"}


def upload_and_process(client, headers):
    from app.tasks import process_document
    with open(DOC, "rb") as f:
        r = client.post("/documents", files={"file": ("nimbus_handbook.md", f)}, headers=headers)
    assert r.status_code == 202
    process_document(r.json()["id"])  # run the job synchronously instead of waiting for a worker
    return r.json()["id"]


def test_requires_auth(client):
    assert client.get("/documents").status_code == 401


def test_full_flow_and_duplicate_upload(client):
    h = signup(client)
    doc_id = upload_and_process(client, h)
    assert client.get(f"/documents/{doc_id}", headers=h).json()["status"] == "ready"
    with open(DOC, "rb") as f:  # same bytes again -> same document, no duplicate chunks
        dup = client.post("/documents", files={"file": ("again.md", f)}, headers=h).json()
    assert dup["duplicate"] is True and dup["id"] == doc_id


@pytest.mark.parametrize("mode", ["vector", "keyword", "hybrid", "hybrid_rerank"])
def test_retrieval_modes_find_evidence(client, mode):
    h = signup(client)
    upload_and_process(client, h)
    r = client.post("/query", json={"question": "How much does the Team plan cost per month?",
                                    "mode": mode, "generate": False}, headers=h)
    assert r.status_code == 200
    assert any("79 dollars" in s["text"] for s in r.json()["sources"])


def test_tenant_isolation(client):
    a, b = signup(client), signup(client)
    upload_and_process(client, a)
    r = client.post("/query", json={"question": "How much does the Team plan cost?", "generate": False}, headers=b)
    assert r.json()["sources"] == []


def test_cache_hit_on_second_identical_query(client):
    h = signup(client)
    upload_and_process(client, h)
    body = {"question": "Which regions does Nimbus operate in?"}
    assert client.post("/query", json=body, headers=h).json()["cached"] is False
    assert client.post("/query", json=body, headers=h).json()["cached"] is True


def test_sse_stream_events(client):
    h = signup(client)
    upload_and_process(client, h)
    r = client.post("/query/stream", json={"question": "What is the API request limit?"}, headers=h)
    text = r.text
    assert text.index("event: sources") < text.index("event: token") < text.index("event: done")


def test_rate_limit_returns_429(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "RATE_CAPACITY", 2.0)
    monkeypatch.setattr(config, "RATE_REFILL_PER_SEC", 0.001)
    h = signup(client)
    codes = [client.post("/query", json={"question": "anything at all", "generate": False}, headers=h).status_code
             for _ in range(4)]
    assert codes[:2] == [200, 200] and 429 in codes[2:]


def test_metrics_endpoint(client):
    h = signup(client)
    m = client.get("/metrics", headers=h).json()
    assert "total_p95_ms" in m and "queue_depth" in m
