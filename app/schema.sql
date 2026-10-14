CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | processing | retrying | ready | failed
    error TEXT,
    chunk_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, content_hash)            -- idempotent uploads: same file twice = same row
);

CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id INT NOT NULL,                     -- denormalised so every search can filter by tenant cheaply
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_user_idx ON chunks (user_id);
CREATE INDEX IF NOT EXISTS chunks_doc_idx ON chunks (document_id);

CREATE TABLE IF NOT EXISTS query_log (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    question TEXT NOT NULL,
    mode TEXT NOT NULL,
    cached BOOLEAN NOT NULL DEFAULT FALSE,
    retrieval_ms DOUBLE PRECISION,
    rerank_ms DOUBLE PRECISION,
    llm_ms DOUBLE PRECISION,
    total_ms DOUBLE PRECISION,
    tokens_in INT,
    tokens_out INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
