-- Knowledge Brain Migration 002: JEV Decision Audit Records

CREATE TABLE IF NOT EXISTS jev_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    decision_id VARCHAR(64) UNIQUE NOT NULL,
    operation_type VARCHAR(32) NOT NULL CHECK (operation_type IN ('ingest', 'retrieve', 'handover', 'conflict', 'maintenance')),
    agent VARCHAR(255),
    model VARCHAR(255),
    provider VARCHAR(64),
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    latency_ms NUMERIC(10, 2) DEFAULT 0.0,
    decision_json JSONB NOT NULL,
    validation_status VARCHAR(32) NOT NULL DEFAULT 'passed' CHECK (validation_status IN ('passed', 'failed', 'rejected')),
    fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jev_decisions_op ON jev_decisions(operation_type);
CREATE INDEX IF NOT EXISTS idx_jev_decisions_created_at ON jev_decisions(created_at);

