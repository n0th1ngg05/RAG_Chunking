# Document Ingestion & Chunking Stack (bare metal)

Local document ingestion pipeline: upload PDF/DOCX/TXT/JPG/JPEG/PNG
→ extract text (OCR fallback for scanned content) → chunk → embed locally via
Ollama → store in Postgres/pgvector.

**Stack:** Node.js (auth, uploads, DB queries, public API) + Python (OCR,
chunking, embeddings, internal worker) + PostgreSQL/pgvector + Redis
(job hand-off) + Ollama (local embeddings). No containers — everything runs
as plain local processes, each reading one shared `.env` at the project root.

See `BUILD_SPEC.md` for the full architecture rationale, reference-repo
analysis, and security decisions this build is based on.

**Layout this README assumes:**

```
docstack/
  .env                 <- one shared env file, both services read it
  sql/init.sql
  node-service/
  python-service/
```

Both `node-service/src/server.js` and `python-service/app/core/config.py`
look for `.env` at this project root (two levels up from each service's
entry point) — keep `node-service/` and `python-service/` as siblings under
one parent folder, as above, or set `UPLOAD_DIR`/paths absolutely and copy
`.env` into each service folder yourself.

---

## 1. Prerequisites (installed locally, not containerized)

- PostgreSQL 16+ with the `pgvector` extension available
  (`CREATE EXTENSION vector;` must succeed)
- Redis server
- Ollama (https://ollama.com) — local embedding model runtime
- Node.js 20+ and npm
- Python 3.11+ and a virtualenv tool
- `tesseract-ocr` and `poppler-utils` (for `pytesseract` / `pdf2image` OCR)
  — e.g. on Debian/Ubuntu: `sudo apt install tesseract-ocr poppler-utils`
- ~6GB free disk for the `nomic-embed-text` model + Postgres data

## 2. First-time setup

```bash
# 1. Copy the env template and fill in real secrets
cp .env.example .env
# Edit .env: set JWT_SECRET to a long random string, and set
# APP_DB_PASSWORD / WORKER_DB_PASSWORD to real values.

# 2. Create the database
createdb docstack

# 3. Edit sql/init.sql: replace CHANGE_ME_APP_PASSWORD and
#    CHANGE_ME_WORKER_PASSWORD with the SAME values you put in .env's
#    APP_DB_PASSWORD / WORKER_DB_PASSWORD. These must match exactly or
#    node-service / python-worker will fail to authenticate.

# 4. Apply the schema (creates tables, roles, RLS policies)
psql -d docstack -f sql/init.sql

# 5. Install Node dependencies
cd node-service
npm install
cd ..

# 6. Set up the Python virtualenv
cd python-service
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cd ..

# 7. Pull the embedding model (Ollama must already be running)
ollama pull nomic-embed-text
```

If you ever need to re-apply the schema from scratch:

```bash
dropdb docstack && createdb docstack
psql -d docstack -f sql/init.sql
```

## 3. Running it

Three long-running processes, each in its own terminal (or under a process
manager like `pm2`/`supervisord`/systemd units if you want them backgrounded):

```bash
# Terminal 1 — make sure these are already running on their default ports:
#   postgres (5432), redis-server (6379), ollama serve (11434)

# Terminal 2 — Node API
cd node-service
npm start

# Terminal 3 — Python worker
cd python-service
. .venv/bin/activate
python -m app.worker
```

Confirm it's up:

```bash
curl http://localhost:3000/health
```

## 4. Using the API

All requests go through node-service on port 3000. The Python worker has no
HTTP server at all — it only reads jobs off Redis.

### Register a user

```bash
curl -X POST http://localhost:3000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Humza",
    "username": "n0th1ng",
    "password": "123",
    "email": "humza@example.com"
  }'
```

### Log in (get a JWT)

```bash
curl -X POST http://localhost:3000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "n0th1ng", "password": "a_strong_password_here"}'
# => { "token": "eyJhbGciOi..." }
```

### Upload a document

```bash
TOKEN="eyJhbGciOi..."   # from login

curl -X POST http://localhost:3000/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/your/document.pdf"
```

This returns immediately (202 Accepted) with the document's id and
`status: "pending"` — ingestion happens asynchronously in the Python worker.

### Check status / list documents

```bash
curl http://localhost:3000/documents/42 -H "Authorization: Bearer $TOKEN"

curl http://localhost:3000/documents -H "Authorization: Bearer $TOKEN"
```

Status moves `pending` → `processing` → `completed` (or `failed`, with
`error_message` populated). A document stuck in `processing` for more than
10 minutes (measured from when the worker actually picked it up, not from
upload time) is automatically swept to `failed` by the worker's own
cron task — no separate process needed for that.

### Fetch chunks once completed

```bash
curl http://localhost:3000/documents/42/chunks -H "Authorization: Bearer $TOKEN"
```

## 5. Ollama models

Only one is required for this pipeline:

```bash
ollama pull nomic-embed-text
```

This is a 768-dimension embedding model, matching the schema's
`VECTOR(768)` column exactly — do not swap in a different-dimension model
(e.g. `mxbai-embed-large` is 1024-dim) without also changing the column
type and `EMBEDDING_DIMENSION` in `.env`.

If you later want local generation/QA over the retrieved chunks (not part
of this ingestion pipeline, but a natural next step):

```bash
ollama pull llama3.1:8b
```

## 6. Resetting everything

```bash
dropdb docstack && createdb docstack
psql -d docstack -f sql/init.sql
redis-cli FLUSHALL
rm -rf uploads/*
```

## 7. Security notes (see BUILD_SPEC.md for full rationale)

- Row-Level Security is enabled on `documents` and `document_chunks`;
  node-service connects as the restricted `app_user` role and sets
  `app.current_user_id` per-transaction. The Python worker connects as
  `worker_user` (BYPASSRLS) since it processes jobs by id, not by session.
- Upload validation checks actual file bytes (magic numbers), not just the
  filename extension or client-supplied MIME type.
- Passwords hashed with bcrypt (12 rounds); login uses a constant-time-ish
  comparison path to avoid leaking whether a username exists via timing.
- All secrets come from `.env` (never committed — see `.gitignore`); the
  app fails fast at startup if required env vars are missing.
- Running bare metal means there's no Docker network isolation around the
  Python worker — it's just a local process. Make sure your firewall/host
  setup doesn't expose Redis or Postgres beyond localhost if this machine
  is reachable from elsewhere.
