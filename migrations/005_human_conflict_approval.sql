-- Migration 005: Human-in-the-Loop Conflict Resolution & Approval Workflow

CREATE TABLE IF NOT EXISTS memory_conflicts (
    id VARCHAR(64) PRIMARY KEY,
    project_id VARCHAR(64) REFERENCES projects(id) ON DELETE SET NULL,
    existing_memory_ids JSONB NOT NULL DEFAULT '[]',
    incoming_claim TEXT NOT NULL,
    source_agent VARCHAR(255) NOT NULL,
    source_session VARCHAR(255),
    evidence_and_provenance JSONB NOT NULL DEFAULT '{}',
    proposed_resolution VARCHAR(32) NOT NULL,
    reason_approval_required TEXT NOT NULL,
    applicable_rule_ids JSONB NOT NULL DEFAULT '[]',
    potentially_affected_documents JSONB NOT NULL DEFAULT '[]',
    potentially_affected_requirements JSONB NOT NULL DEFAULT '[]',
    potentially_affected_tasks JSONB NOT NULL DEFAULT '[]',
    status VARCHAR(32) NOT NULL DEFAULT 'pending_human_approval' CHECK (
        status IN ('detected', 'evaluating', 'pending_human_approval', 'approved', 'rejected', 'clarification_required', 'resolved')
    ),
    human_approver VARCHAR(255),
    approval_rationale TEXT,
    clarification_request TEXT,
    clarification_response TEXT,
    execution_status VARCHAR(32) NOT NULL DEFAULT 'pending' CHECK (
        execution_status IN ('pending', 'executed', 'rejected', 'skipped')
    ),
    synchronization_status VARCHAR(64) NOT NULL DEFAULT 'pending',
    existing_state_snapshot JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_conflicts_status ON memory_conflicts(status);
CREATE INDEX IF NOT EXISTS idx_memory_conflicts_project ON memory_conflicts(project_id);
CREATE INDEX IF NOT EXISTS idx_memory_conflicts_created ON memory_conflicts(created_at);

-- Audit log for human decisions on conflicts
CREATE TABLE IF NOT EXISTS conflict_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conflict_id VARCHAR(64) NOT NULL REFERENCES memory_conflicts(id) ON DELETE CASCADE,
    actor VARCHAR(255) NOT NULL,
    actor_type VARCHAR(32) NOT NULL CHECK (actor_type IN ('human', 'agent', 'system')),
    action VARCHAR(32) NOT NULL,
    decision VARCHAR(32),
    rationale TEXT,
    previous_status VARCHAR(32),
    new_status VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conflict_audit_conflict ON conflict_audit_log(conflict_id);

