-- Knowledge Brain Migration: Task Ownership & Checkpoint Versioning

-- Ensure tasks table has status, current_owner, and updated_at
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'in_progress';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS current_owner TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Ensure checkpoints table has git_commit and git_branch
ALTER TABLE checkpoints ADD COLUMN IF NOT EXISTS git_commit TEXT;
ALTER TABLE checkpoints ADD COLUMN IF NOT EXISTS git_branch TEXT;

-- Create indexes for performance and concurrency
CREATE INDEX IF NOT EXISTS idx_tasks_current_owner ON tasks(current_owner);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_checkpoints_created_at ON checkpoints(created_at);

