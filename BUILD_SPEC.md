# Document Ingestion & Chunking Stack — Build Spec / Context Handoff

Paste this entire file into a new Claude session if context runs out. It contains
everything needed to continue or rebuild this project from scratch.

## 1. Goal

Build a local, Dockerized document-ingestion + RAG-chunking stack:
upload a document (PDF/DOCX/TXT/JPG/JPEG/PNG) → extract text (OCR if needed) →
chunk it → embed chunks locally via Ollama → store in Postgres/pgvector →
queryable for retrieval later.

## 2. Tech stack (fixed, do not change without explicit request)

- **Backend/middleware (public-facing):** Node.js (Express) — auth, request handling,
  all direct DB queries, file upload endpoint, enqueues ingestion jobs.
- **Processing worker (internal only, never exposed on a host port):** Python (FastAPI
  optional, or a plain worker loop) — OCR, chunking, embedding generation, pgvector writes.
- **DB:** PostgreSQL + pgvector extension.
- **Queue:** Redis + a job queue (BullMQ on the Node side enqueuing; Python worker
  consumes from Redis — mirrors the ARQ pattern below).
- **Embeddings:** Local Ollama, model `nomic-embed-text` (768-dim, matches schema).
- **Auth:** JWT (HS256) + PostgreSQL Row-Level Security (RLS) — RLS policies are a
  hard requirement, not optional, per explicit user decision.
- **Containerization:** Docker Compose, 5 services: postgres, redis, ollama,
  node-service, python-worker. Python worker has no published host port — Node
  reaches it only over the internal Docker network.

## 3. Reference repository (already analyzed, in /mnt/user-data/uploads/offline_ai.zip)

A FastAPI reference project ("offline_ai") was supplied and inspected. It is NOT
Node.js and NOT local-embeddings — it's a fully different stack (FastAPI only,
OpenAI embeddings/vision) — so it is NOT a drop-in. However these specific pieces
are worth lifting and adapting:

- `app/services/vector_store.py` → `hybrid_chunk_text()`: paragraph-first chunking
  with sentence-level fallback for oversized blocks, with overlap. Reuse this
  algorithm directly (just reimplement in Python, same logic) for the chunker.
- `app/workers/arq_worker.py`: ARQ + Redis job queue pattern, with a cron sweeper
  (`sweep_stuck_jobs`) that reclaims jobs stuck in "processing" for >5 min after a
  crash. This solves the user's original "keep Python process alive, decide
  whether to spawn/kill" requirement — copy this pattern (status sweep + timeout +
  max_jobs cap), not a manually-managed long-lived process.
- `app/core/security.py`: JWT validation pattern (decode → look up user → check
  active status) — reusable logic, adapt to the new `users` table shape below.
- `app/models/vector_store.py` (ContentChunk): same general shape as the new
  `document_chunks` table, but is missing `page_number` and `metadata JSONB` and
  has no unique constraint on (document_id, chunk_index) — the new schema below
  fixes both gaps.

Known issues in the reference repo, explicitly NOT to carry over:
- Hardcoded absolute path (`/var/www/html/offlineai/fastapi`) in vector_store.py —
  never hardcode paths; use env-configured base paths.
- Two parallel auth dependency functions resolving against two different user
  tables with inconsistent status casing (`"active"` vs `"ACTIVE"`) — single user
  table, single auth path only in the new build.
- No file-type/MIME validation on upload — new build must validate both extension
  and actual file signature (magic bytes), not just trust the client-sent MIME type.
- No RLS anywhere — new build must implement real RLS policies.
- `.env` committed to the repo — never commit real secrets; `.env.example` only.

## 4. Database schema (final, as specified by user — do not alter field names/types)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL,
    dob             DATE,
    username        VARCHAR(50) UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    email           VARCHAR(254) UNIQUE NOT NULL,
    contact_no      VARCHAR(20),
    user_type       VARCHAR(30) NOT NULL DEFAULT 'user',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE documents (
    id              BIGSERIAL PRIMARY KEY,
    document_name   VARCHAR(255) NOT NULL,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    uploaded_by     BIGINT NOT NULL REFERENCES users(id),
    size_bytes      BIGINT NOT NULL CHECK (size_bytes >= 0),
    file_type       VARCHAR(20) NOT NULL CHECK (file_type IN
                        ('JPG','JPEG','PNG','PDF','DOCX','TXT')),
    mime_type       VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN
                        ('pending','processing','completed','failed'))
);

CREATE TABLE document_chunks (
    id              BIGSERIAL PRIMARY KEY,
    document_id     BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    embedding       VECTOR(768) NOT NULL,
    page_number     INTEGER,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX idx_documents_uploaded_by ON documents(uploaded_by);
CREATE INDEX idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Row-Level Security
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_owner_policy ON documents
    USING (uploaded_by = current_setting('app.current_user_id')::BIGINT);

CREATE POLICY chunks_owner_policy ON document_chunks
    USING (document_id IN (
        SELECT id FROM documents
        WHERE uploaded_by = current_setting('app.current_user_id')::BIGINT
    ));
```

Node sets `app.current_user_id` via `SET LOCAL` at the start of every transaction,
from the authenticated JWT's user id, before running any query.

## 5. Security requirements (explicit decisions from the review conversation)

1. Python worker container: NO published host port. Only reachable by Node over
   the Docker internal network (`python-worker:8000` style hostname).
2. Node DB layer: parameterized queries only (pg library `$1,$2` placeholders or
   an ORM) — raw string concatenation into SQL is explicitly forbidden.
3. RLS policies must be real, tested code — not just documented intent.
4. Upload validation: check both file extension AND magic bytes (e.g. via
   `file-type` npm package), reject on mismatch.
5. Secrets via `.env`, never committed; `.env.example` with placeholders only.
6. JWT secret, DB creds, Redis — all via environment variables, validated at
   startup (fail fast if missing).
7. Resource limits on python-worker container (`cpus`, `mem_limit` in compose)
   and on the queue (`max_jobs`, `job_timeout`, matching the ARQ pattern's
   `max_jobs=10, job_timeout=600`).

## 6. Deliverables checklist

- [ ] `docker-compose.yml` — 5 services (postgres w/ pgvector, redis, ollama,
      node-service, python-worker), volumes, internal-only networking for
      python-worker, resource limits.
- [ ] `sql/init.sql` — schema above, applied on postgres container init.
- [ ] `node-service/` — Express app: JWT auth (register/login), file upload
      endpoint (multer, validates type+size+magic bytes), enqueues job to Redis,
      status polling endpoint, RLS context-setting middleware, parameterized `pg`
      queries only.
- [ ] `python-worker/` — consumes queue jobs, extracts text (pypdf / python-docx /
      pytesseract for images / PyMuPDF or pdf2image+tesseract for scanned PDFs),
      runs the hybrid chunker (ported from reference repo), calls local Ollama
      `/api/embeddings` with `nomic-embed-text`, writes chunks to
      `document_chunks`, updates `documents.status`.
- [ ] Ollama model pull instructions (`nomic-embed-text`).
- [ ] README / run instructions: `docker compose up`, pull Ollama model, apply
      schema, example curl calls for register/login/upload/status.

## 7. Open decisions the user has NOT yet specified (ask, don't assume, if resuming)

- Exact Node framework preference beyond "Node.js" (assumed Express + `pg` + `bullmq`
  unless told otherwise).
- Whether document files are stored on local disk (bind-mounted volume shared
  between node-service and python-worker) or object storage — assumed local
  bind-mounted volume (`./uploads`) for this local/offline-first build.
- Max upload size limit — not specified, use a sane default (e.g. 25MB) and flag
  it as adjustable.
