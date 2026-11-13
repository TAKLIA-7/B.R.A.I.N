-- Migration 003: Project Knowledge and Dynamic Evolution Architecture
-- Establishes projects, project documents, requirements, versioning, change requests, approvals, impacts, and log events.

-- 1. Projects
CREATE TABLE IF NOT EXISTS projects (
    id VARCHAR(64) PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    repository_url TEXT,
    root_path TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

-- 2. Project Documents (Metadata and Synchronization state)
CREATE TABLE IF NOT EXISTS project_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id VARCHAR(64) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_type VARCHAR(64) NOT NULL,
    relative_path TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    content_hash VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'synced' CHECK (status IN ('synced', 'outdated', 'conflict', 'unregistered')),
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project_id, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_project_docs_project_id ON project_documents(project_id);
CREATE INDEX IF NOT EXISTS idx_project_docs_status ON project_documents(status);

-- 3. Requirements (Canonical Requirement Registry)
CREATE TABLE IF NOT EXISTS requirements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    req_id VARCHAR(64) UNIQUE NOT NULL,
    project_id VARCHAR(64) REFERENCES projects(id) ON DELETE CASCADE,
    module VARCHAR(64) NOT NULL,
    title TEXT NOT NULL,
    category VARCHAR(32) NOT NULL DEFAULT 'functional' CHECK (category IN ('functional', 'non_functional', 'security', 'api', 'architecture', 'database')),
    priority VARCHAR(32) NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    current_version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(32) NOT NULL DEFAULT 'approved' CHECK (status IN ('draft', 'proposed', 'approved', 'deprecated')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_requirements_project_id ON requirements(project_id);
CREATE INDEX IF NOT EXISTS idx_requirements_req_id ON requirements(req_id);
CREATE INDEX IF NOT EXISTS idx_requirements_status ON requirements(status);

-- 4. Requirement Versions (Immutable History)
CREATE TABLE IF NOT EXISTS requirement_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    requirement_id UUID NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    description TEXT NOT NULL,
    acceptance_criteria JSONB NOT NULL DEFAULT '[]',
    source TEXT,
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approval_status VARCHAR(32) NOT NULL DEFAULT 'proposed' CHECK (approval_status IN ('proposed', 'approved', 'rejected', 'superseded')),
    approved_by VARCHAR(255),
    approved_at TIMESTAMPTZ,
    supersedes_version INTEGER,
    UNIQUE(requirement_id, version)
);

CREATE INDEX IF NOT EXISTS idx_req_versions_req_id ON requirement_versions(requirement_id);
CREATE INDEX IF NOT EXISTS idx_req_versions_version ON requirement_versions(requirement_id, version);

-- 5. Change Requests
CREATE TABLE IF NOT EXISTS change_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    change_id VARCHAR(64) UNIQUE NOT NULL,
    req_id VARCHAR(64) NOT NULL REFERENCES requirements(req_id) ON DELETE CASCADE,
    target_version INTEGER NOT NULL,
    original_value TEXT,
    proposed_value TEXT NOT NULL,
    reason TEXT NOT NULL,
    source TEXT,
    proposed_by VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'approved', 'rejected', 'applied')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_change_requests_req_id ON change_requests(req_id);

-- 6. Change Approvals (Audit log)
CREATE TABLE IF NOT EXISTS change_approvals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    change_id VARCHAR(64) NOT NULL REFERENCES change_requests(change_id) ON DELETE CASCADE,
    decision VARCHAR(32) NOT NULL CHECK (decision IN ('approved', 'rejected')),
    approver VARCHAR(255) NOT NULL,
    rationale TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_change_approvals_change_id ON change_approvals(change_id);

-- 7. Requirement Impacts
CREATE TABLE IF NOT EXISTS requirement_impacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    req_id VARCHAR(64) NOT NULL,
    version INTEGER NOT NULL,
    affected_modules JSONB NOT NULL DEFAULT '[]',
    affected_files JSONB NOT NULL DEFAULT '[]',
    affected_endpoints JSONB NOT NULL DEFAULT '[]',
    affected_entities JSONB NOT NULL DEFAULT '[]',
    affected_tasks JSONB NOT NULL DEFAULT '[]',
    affected_tests JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_req_impacts_req_id ON requirement_impacts(req_id, version);

-- 8. Alter tasks table to add requirement linkages and staleness tracking
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS target_requirement_id VARCHAR(64);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS target_requirement_version INTEGER;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT FALSE;

-- 9. Runtime Log Events
CREATE TABLE IF NOT EXISTS log_events (
    id BIGSERIAL PRIMARY KEY,
    project_id VARCHAR(64),
    task_id VARCHAR(255),
    agent_id VARCHAR(255),
    service VARCHAR(64),
    severity VARCHAR(32) DEFAULT 'info',
    normalized_message TEXT NOT NULL,
    trace_id VARCHAR(64),
    request_id VARCHAR(64),
    bug_id VARCHAR(64),
    raw_log_reference TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_log_events_project ON log_events(project_id);
CREATE INDEX IF NOT EXISTS idx_log_events_task ON log_events(task_id);
CREATE INDEX IF NOT EXISTS idx_log_events_severity ON log_events(severity);

