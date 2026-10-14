"""Load test:  locust -f loadtest/locustfile.py --host http://localhost:8000 --users 50 --spawn-rate 5 --run-time 60s --headless
Retrieval-only (generate=false) so it measures the search stack without spending LLM tokens.
Upload a document first (see README) so searches have something to find."""
import random
import uuid

from locust import HttpUser, between, task

QUESTIONS = [
    "How much does the Team plan cost per month?", "How many times will a crashed pod be restarted?",
    "Which regions are supported?", "What happens when the API limit is exceeded?",
    "How long are logs retained?", "Is there an annual prepayment discount?",
]


class RagUser(HttpUser):
    wait_time = between(0.2, 1.0)

    def on_start(self):
        email = f"load-{uuid.uuid4().hex[:10]}@test.io"
        r = self.client.post("/auth/register", json={"email": email, "password": "password123"})
        self.headers = {"Authorization": f"Bearer {r.json()['token']}"}
        with open("eval/docs/nimbus_handbook.md", "rb") as f:
            self.client.post("/documents", files={"file": ("nimbus_handbook.md", f)}, headers=self.headers)

    @task
    def ask(self):
        with self.client.post("/query", headers=self.headers, catch_response=True,
                              json={"question": random.choice(QUESTIONS), "mode": "hybrid_rerank", "generate": False}) as r:
            if r.status_code == 429:
                r.success()  # rate limiting working as designed is not a failure
