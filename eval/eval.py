"""Evaluation harness.  Run from the project root:

    python -m eval.eval --chunk-sizes 200 350 500            (real documents)
    python -m eval.eval --chunk-sizes 40 80 120 --judge      (sample doc; --judge needs ANTHROPIC_API_KEY)

For each chunk size it re-ingests eval/docs/*, then runs every retrieval mode over eval/golden.json
and reports recall@1/3/5 and MRR. Results are also written to eval/results.md.
"""
import argparse
import glob
import json
import os
import statistics

from app import db, llm
from app.auth import hash_password
from app.ingest import ingest_document, sha256_bytes
from app.search import MODES, retrieve
from eval.metrics import hit_rank, mrr, recall_at_k

HERE = os.path.dirname(__file__)
EVAL_EMAIL = "eval@local"


def ensure_user(conn) -> int:
    row = conn.execute("SELECT id FROM users WHERE email=%s", (EVAL_EMAIL,)).fetchone()
    if row:
        return row["id"]
    return conn.execute("INSERT INTO users (email, password_hash) VALUES (%s,%s) RETURNING id",
                        (EVAL_EMAIL, hash_password("eval-user-not-for-login"))).fetchone()["id"]


def reingest(conn, user_id: int, size: int) -> int:
    conn.execute("DELETE FROM documents WHERE user_id=%s", (user_id,))
    total = 0
    for path in sorted(glob.glob(os.path.join(HERE, "docs", "*"))):
        if not path.lower().endswith((".txt", ".md", ".pdf", ".docx")):
            continue
        with open(path, "rb") as f:
            digest = sha256_bytes(f.read())
        doc_id = conn.execute("INSERT INTO documents (user_id, filename, content_hash) VALUES (%s,%s,%s) RETURNING id",
                              (user_id, os.path.basename(path), digest)).fetchone()["id"]
        total += ingest_document(conn, doc_id, user_id, path, chunk_size=size, overlap=max(1, size // 6))
    return total


def judge_faithful(question: str, answer: str, chunks: list[dict]) -> bool:
    ctx = "\n\n".join(c["content"] for c in chunks)
    verdict = llm.complete(
        "You are a strict grader. Reply with exactly YES or NO.",
        f"Context:\n{ctx}\n\nAnswer to grade:\n{answer}\n\n"
        "Is every factual claim in the answer supported by the context? (An answer saying it does not know is supported.)",
        max_tokens=5)
    return verdict.strip().upper().startswith("YES")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk-sizes", type=int, nargs="+", default=[200, 350])
    ap.add_argument("--judge", action="store_true", help="LLM-as-judge faithfulness for hybrid_rerank (needs API key)")
    ap.add_argument("--golden", default=os.path.join(HERE, "golden.json"))
    args = ap.parse_args()

    golden = json.load(open(args.golden))
    pool = db.get_pool()
    lines = ["| chunk size (words) | mode | recall@1 | recall@3 | recall@5 | MRR | median latency (ms) |",
             "|---|---|---|---|---|---|---|"]
    faith_lines = []
    with pool.connection() as conn:
        uid = ensure_user(conn)
        for size in args.chunk_sizes:
            n_chunks = reingest(conn, uid, size)
            print(f"chunk size {size}: {n_chunks} chunks")
            for mode in MODES:
                ranks, lat = [], []
                for item in golden:
                    chunks, t = retrieve(conn, uid, item["question"], mode, top_k=5)
                    ranks.append(hit_rank([c["content"] for c in chunks], item["evidence"]))
                    lat.append(t["retrieval_ms"] + t["rerank_ms"])
                lines.append(f"| {size} | {mode} | {recall_at_k(ranks,1):.2f} | {recall_at_k(ranks,3):.2f} | "
                             f"{recall_at_k(ranks,5):.2f} | {mrr(ranks):.2f} | {statistics.median(lat):.0f} |")
            if args.judge:
                ok = 0
                for item in golden:
                    chunks, _ = retrieve(conn, uid, item["question"], "hybrid_rerank", top_k=5)
                    answer = "".join(v for k, v in llm.stream_answer(item["question"], chunks) if k == "token")
                    ok += judge_faithful(item["question"], answer, chunks)
                faith_lines.append(f"- chunk size {size}: faithfulness {ok}/{len(golden)} = {ok/len(golden):.2f}")
    out = "\n".join(lines)
    if faith_lines:
        out += "\n\nFaithfulness (LLM-as-judge, hybrid_rerank):\n" + "\n".join(faith_lines)
    print("\n" + out)
    with open(os.path.join(HERE, "results.md"), "w") as f:
        f.write(out + "\n")


if __name__ == "__main__":
    main()
