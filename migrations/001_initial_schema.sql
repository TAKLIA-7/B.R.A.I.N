-- Knowledge Brain Canonical Schema Migration 001
-- Enables UUID and pgvector extensions, defines authoritative tables and constraints

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 1. Sources (provenance and trust state)
CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type VARCHAR(64) NOT NULL,
    actor VARCHAR(255) NOT NULL,
    trust_level NUMERIC(3, 2) NOT NULL DEFAULT 0.50,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Memories (canonical persistent records and semantic index)
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type VARCHAR(64) NOT NULL,
    subject VARCHAR(255),
    predicate VARCHAR(255),
    object TEXT,
    text TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'deleted')),
    epistemic_state VARCHAR(32) NOT NULL DEFAULT 'asserted' CHECK (epistemic_state IN ('asserted', 'confirmed', 'disputed')),
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    message_ref VARCHAR(255),
    valid_from TIMESTAMPTZ DEFAULT NOW(),
    valid_until TIMESTAMPTZ,
    supersedes_id UUID REFERENCES memories(id) ON DELETE SET NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
CREATE INDEX IF NOT EXISTS idx_memories_epistemic_state ON memories(epistemic_state);
CREATE INDEX IF NOT EXISTS idx_memories_source_id ON memories(source_id);
CREATE INDEX IF NOT EXISTS idx_memories_validity ON memories(valid_from, valid_until);

-- 3. Tasks (high-level agent goals and metadata)
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(255) PRIMARY KEY,
    goal TEXT NOT NULL,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Checkpoints (durable state persistence for tasks)
CREATE TABLE IF NOT EXISTS checkpoints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id VARCHAR(255) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    state_json JSONB NOT NULL,
    written_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_task_version UNIQUE(task_id, version)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_task ON checkpoints(task_id, version);

-- 5. Call Log (MCP telemetry and audit log)
CREATE TABLE IF NOT EXISTS call_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent VARCHAR(255),
    tool VARCHAR(255) NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    latency_ms NUMERIC(10, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. Deletions (audit receipts for verified forgetting)
CREATE TABLE IF NOT EXISTS deletions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scope VARCHAR(255) NOT NULL,
    status VARCHAR(64) NOT NULL,
    receipt_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. Bugs (structured defect tracking)
CREATE TABLE IF NOT EXISTS bugs (
    bug_id VARCHAR(64) PRIMARY KEY,
    title TEXT NOT NULL,
    symptom TEXT,
    root_cause TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'fixed', 'verified', 'wontfix', 'regressed')),
    severity VARCHAR(32) DEFAULT 'medium',
    location JSONB,
    signature VARCHAR(255),
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reported_by VARCHAR(255),
    epistemic_state VARCHAR(32) NOT NULL DEFAULT 'asserted' CHECK (epistemic_state IN ('asserted', 'confirmed', 'disputed'))
);

CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status);
CREATE INDEX IF NOT EXISTS idx_bugs_signature ON bugs(signature);

-- 8. Attempts (investigation attempts including failed/partial)
CREATE TABLE IF NOT EXISTS attempts (
    attempt_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    bug_id VARCHAR(64) NOT NULL REFERENCES bugs(bug_id) ON DELETE CASCADE,
    agent VARCHAR(255),
    hypothesis TEXT,
    action TEXT,
    outcome VARCHAR(32) NOT NULL CHECK (outcome IN ('failed', 'partial', 'succeeded')),
    evidence JSONB,
    learned TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_attempts_bug_id ON attempts(bug_id);

-- 9. Fixes (resolution records and verification evidence)
CREATE TABLE IF NOT EXISTS fixes (
    fix_id VARCHAR(64) PRIMARY KEY,
    bug_id VARCHAR(64) NOT NULL REFERENCES bugs(bug_id) ON DELETE CASCADE,
    commit VARCHAR(255),
    files_changed JSONB,
    summary TEXT,
    verification JSONB,
    fixed_by VARCHAR(255),
    supersedes_fix VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fixes_bug_id ON fixes(bug_id);

-- 10. Bug Events (append-only state transitions)
CREATE TABLE IF NOT EXISTS bug_events (
    id BIGSERIAL PRIMARY KEY,
    bug_id VARCHAR(64) NOT NULL REFERENCES bugs(bug_id) ON DELETE CASCADE,
    event VARCHAR(64) NOT NULL,
    from_status VARCHAR(32),
    to_status VARCHAR(32),
    agent VARCHAR(255),
    reason TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bug_events_bug_id ON bug_events(bug_id);

-- 11. Bug Relations (duplicate_of, caused_by, regression_of, related_to)
CREATE TABLE IF NOT EXISTS bug_relations (
    bug_id VARCHAR(64) NOT NULL REFERENCES bugs(bug_id) ON DELETE CASCADE,
    related_bug_id VARCHAR(64) NOT NULL REFERENCES bugs(bug_id) ON DELETE CASCADE,
    relation_type VARCHAR(32) NOT NULL CHECK (relation_type IN ('related_to', 'duplicate_of', 'caused_by', 'regression_of')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (bug_id, related_bug_id, relation_type)
);

-- 12. Outbox Events (reliable synchronization for derived stores like Neo4j)
CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbox_events_status ON outbox_events(status);

