-- Migration 004: Proactive AI Agent Checkpointing and Context Monitoring
-- Establishes task-to-project links and checkpoint trigger audit logging.

-- 1. Add project_id to tasks if not present
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_id VARCHAR(64) REFERENCES projects(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);

-- 2. Checkpoint Triggers & Telemetry Audit Table
CREATE TABLE IF NOT EXISTS checkpoint_triggers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id VARCHAR(255) NOT NULL,
    project_id VARCHAR(64),
    agent_name VARCHAR(255) NOT NULL,
    session_id VARCHAR(255),
    trigger_reason VARCHAR(64) NOT NULL,
    context_percentage NUMERIC(5, 2),
    tokens_consumed INTEGER,
    tokens_capacity INTEGER,
    checkpoint_version INTEGER,
    idempotency_key VARCHAR(255) UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'completed',
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_checkpoint_triggers_task ON checkpoint_triggers(task_id);
CREATE INDEX IF NOT EXISTS idx_checkpoint_triggers_project ON checkpoint_triggers(project_id);
CREATE INDEX IF NOT EXISTS idx_checkpoint_triggers_created ON checkpoint_triggers(created_at);

