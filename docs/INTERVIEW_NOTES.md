# Interview notes — be able to answer these without looking

**30-second pitch.** "A multi-tenant RAG backend. Uploads are processed asynchronously through a Redis queue with idempotent,
retrying workers. Search is hybrid — Postgres full-text plus pgvector fused with Reciprocal Rank Fusion, then a cross-encoder
rerank. Answers stream over SSE with citations. I built an eval harness that measures recall@k and MRR, so I could show which
retrieval setup is actually better, and I load-tested it."

1. **Why a queue?** Embedding a document takes seconds; blocking an HTTP request hurts latency and fails on timeouts. The queue decouples ingestion from serving, lets me scale workers independently, and gives retries.
2. **What does idempotent mean here and why does it matter?** Queues deliver at-least-once, so a job can run twice (crash after work, before ack). My worker deletes and re-inserts a document's chunks in one transaction, and uploads dedupe on (user, SHA-256), so repeats never create duplicates.
3. **What happens when a job keeps failing?** Status goes `retrying` with backoff (10/30/90s). After the last retry the document is `failed` with the error and the job stays in RQ's failed registry (dead-letter queue). `/documents/{id}/retry` re-enqueues it.
4. **Why pgvector instead of Chroma/Pinecone?** One system for transactions, tenant filtering, full-text and vectors, so fewer moving parts and consistent deletes. Trade-off: a specialised engine scales further. HNSW index = approximate nearest neighbour (fast, slightly lossy).
5. **Vector vs keyword search?** Vectors match meaning ("car" ≈ "automobile") but can miss exact tokens (error codes, names). Keyword search is the reverse. Hybrid covers both.
6. **What is RRF?** `score = Σ 1/(60 + rank)` over each ranking. It merges lists using ranks only, so I don't have to normalise incomparable scores (cosine vs ts_rank).
7. **Bi-encoder vs cross-encoder?** Bi-encoder embeds query and chunk separately, so chunk vectors are precomputed (fast, approximate). Cross-encoder reads query and chunk together (accurate, too slow for everything), so it only rescores the shortlist.
8. **How did you choose chunk size?** Measured: the eval harness re-ingests with several sizes and compares recall@k/MRR. Too big dilutes meaning and wastes context; too small loses context. Overlap protects answers that straddle a boundary.
9. **How do you measure answer quality?** Retrieval: recall@k and MRR against a golden set (relevance = evidence phrase appears in the chunk). Generation: optional LLM-as-judge faithfulness. Limitation: judge is noisy, golden set is small.
10. **How do you reduce hallucination?** The prompt restricts the model to numbered passages, requires citations and allows "I don't know". Sources are sent first over SSE so users can verify.
11. **How is tenant data isolated?** `user_id` on every chunk and a filter in every query; tests assert user B gets nothing from user A's docs. At scale: Postgres row-level security.
12. **How does rate limiting work?** Token bucket in Redis updated by a Lua script, atomic across API instances. Tokens refill continuously; empty bucket → HTTP 429 + Retry-After.
13. **Caching pitfalls?** Stale answers after a document changes. The key includes a corpus version (max id + count of ready docs), so changes invalidate it.
14. **What bug did you hit?** RQ forks per job, and the Postgres pool inherited from the parent shared sockets across processes ("SSL error: decryption failed"). Fix: pool is per-process and rebuilt when the pid changes.
15. **What would you do at 100x?** Shard/replicate Postgres or move vectors to a dedicated store; autoscale workers on queue depth; batch embeddings on GPU; async LLM calls; per-tenant quotas; observability with traces; row-level security.
