-- ============================================================
-- Document Ingestion Stack — Schema Init
-- Bare-metal: apply manually once, after creating the docstack DB, e.g.:
--   createdb docstack
--   psql -d docstack -f sql/init.sql
-- (Replace CHANGE_ME_APP_PASSWORD / CHANGE_ME_WORKER_PASSWORD below first —
-- see the note near the role creation statements.)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ------------------------------------------------------------
-- Users
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- Documents
-- ------------------------------------------------------------
CREATE TABLE documents (
    id              BIGSERIAL PRIMARY KEY,
    document_name   VARCHAR(255) NOT NULL,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    uploaded_by     BIGINT NOT NULL REFERENCES users(id),
    size_bytes      BIGINT NOT NULL CHECK (size_bytes >= 0),
    file_type       VARCHAR(20) NOT NULL CHECK (file_type IN
                        ('JPG', 'JPEG', 'PNG', 'PDF', 'DOCX', 'TXT')),
    mime_type       VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN
                        ('pending', 'processing', 'completed', 'failed')),
    storage_path    VARCHAR(500) NOT NULL,
    error_message   TEXT,
    -- Set by python-worker when it picks up a job (see ingestion.py). The
    -- stuck-job sweeper in worker.py uses THIS, not uploaded_at, as its
    -- cutoff — otherwise a document still legitimately mid-OCR past 10
    -- minutes after upload gets wrongly marked failed by the sweep.
    processing_started_at TIMESTAMPTZ,
    -- Persisted document ingestion performance telemetry and stage durations
    metrics         JSONB NOT NULL DEFAULT '{}'
);

-- ------------------------------------------------------------
-- Document Chunks
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- Indexes
-- ------------------------------------------------------------
CREATE INDEX idx_documents_uploaded_by ON documents(uploaded_by);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_chunks_document_id ON document_chunks(document_id);

-- IVFFlat index for cosine-similarity vector search.
-- NOTE: ivfflat needs rows in the table to build well; with very little data
-- early on, index quality is poor. Safe to create now, fine either way.
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ------------------------------------------------------------
-- Row-Level Security
-- ------------------------------------------------------------
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;

-- The app sets `app.current_user_id` via `SET LOCAL` at the top of every
-- transaction (see node-service/src/db/withUserContext.js). Policies below
-- then transparently filter every query to that user's own rows.
--
-- app_user role: application connects as this role, not as the postgres
-- superuser, so RLS is actually enforced (table owners / superusers bypass
-- RLS by default in Postgres).
--
-- BARE-METAL NOTE: this file is applied manually (`psql -f sql/init.sql`),
-- not auto-run by a container entrypoint. Before running it, replace
-- CHANGE_ME_APP_PASSWORD / CHANGE_ME_WORKER_PASSWORD below with the SAME
-- values you put in APP_DB_PASSWORD / WORKER_DB_PASSWORD in .env — these
-- must match or node-service / python-worker will fail to authenticate.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user LOGIN PASSWORD 'n0th1ng#1234';
    END IF;
END
$$;

-- Fixed: previously granted CONNECT on the "postgres" maintenance database
-- instead of this app's actual database. Harmless today only because a
-- freshly created DB grants PUBLIC the CONNECT privilege by default; it
-- would silently break if that default is ever revoked, so grant it
-- explicitly on docstack instead.
GRANT CONNECT ON DATABASE docstack TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE ON users TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON documents TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON document_chunks TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

CREATE POLICY documents_owner_select ON documents
    FOR SELECT
    USING (uploaded_by = current_setting('app.current_user_id', true)::BIGINT);

CREATE POLICY documents_owner_insert ON documents
    FOR INSERT
    WITH CHECK (uploaded_by = current_setting('app.current_user_id', true)::BIGINT);

CREATE POLICY documents_owner_update ON documents
    FOR UPDATE
    USING (uploaded_by = current_setting('app.current_user_id', true)::BIGINT);

CREATE POLICY documents_owner_delete ON documents
    FOR DELETE
    USING (uploaded_by = current_setting('app.current_user_id', true)::BIGINT);

CREATE POLICY chunks_owner_select ON document_chunks
    FOR SELECT
    USING (document_id IN (
        SELECT id FROM documents
        WHERE uploaded_by = current_setting('app.current_user_id', true)::BIGINT
    ));

CREATE POLICY chunks_owner_insert ON document_chunks
    FOR INSERT
    WITH CHECK (document_id IN (
        SELECT id FROM documents
        WHERE uploaded_by = current_setting('app.current_user_id', true)::BIGINT
    ));

CREATE POLICY chunks_owner_delete ON document_chunks
    FOR DELETE
    USING (document_id IN (
        SELECT id FROM documents
        WHERE uploaded_by = current_setting('app.current_user_id', true)::BIGINT
    ));

-- The python-worker connects as a separate, trusted role that bypasses RLS
-- (it legitimately needs to write chunks for any user's document, identified
-- by job payload, not by a logged-in session). It never serves HTTP directly
-- to end users, so this is safe.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'worker_user') THEN
        CREATE ROLE worker_user LOGIN PASSWORD 'n0th1ng#1234' BYPASSRLS;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE docstack TO worker_user;
GRANT USAGE ON SCHEMA public TO worker_user;
GRANT SELECT, UPDATE ON documents TO worker_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON document_chunks TO worker_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO worker_user;
