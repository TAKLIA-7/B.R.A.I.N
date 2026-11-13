# Proactive AI Agent Checkpointing & Context Monitoring

Knowledge Brain includes a proactive checkpointing architecture that automatically updates a project's `checkpoint.md` file and persists versioned milestones to PostgreSQL when an AI coding agent's context window approaches exhaustion.

This ensures that critical development progress, uncommitted Git changes, architectural decisions, and pending tasks are preserved before the agent loses working context or hits memory compaction.

---

## 1. Architecture Overview

```
                                  ┌───────────────────────────────────────────────┐
                                  │               AI Coding Agent                 │
                                  │   (Google Antigravity, OpenAI Codex, etc.)    │
                                  └───────────────┬───────────────────────────────┘
                                                  │ Telemetry / Compaction Event
                                                  ▼
                                  ┌───────────────────────────────────────────────┐
                                  │          Agent Usage Monitoring System        │
                                  │  ├── AntigravityAdapter                       │
                                  │  ├── CodexAdapter                             │
                                  │  └── UsageMonitor (Policy: 70%, 80%, 90%, 95%)│
                                  └──────────────────────┬────────────────────────┘
                                                         │ Threshold Trigger
                                                         ▼
                                  ┌───────────────────────────────────────────────┐
                                  │             Checkpoint Scheduler              │
                                  │  ├── GitInspector (diffs, status, branch)     │
                                  │  ├── CheckpointMarkdownGenerator (Sec A-H)   │
                                  │  └── Concurrency & Idempotency Controller     │
                                  └──────────────┬──────────────────┬─────────────┘
                                                 │                  │
                         Canonical Persistence   ▼                  ▼   Human-Readable Projection
                      ┌────────────────────────────┐      ┌─────────────────────────────┐
                      │    PostgreSQL 16 Core      │      │    Project Markdown Sync    │
                      │ • `tasks`                  │      │ • `projects/<id>/           │
                      │ • `checkpoints` (v1..vN)   │      │    checkpoint.md`           │
                      │ • `checkpoint_triggers`    │      │ • `checkpoints/             │
                      │ • `project_documents`      │      │    checkpoint_v{N}.md`      │
                      └────────────────────────────┘      └─────────────────────────────┘
```

---

## 2. Supported Agents & Adapter Architecture

The monitoring system uses an extensible adapter architecture under `agent_monitor/`:

```text
agent_monitor/
├── base_adapter.py          # Abstract BaseAgentAdapter & AgentUsageMetrics
├── antigravity_adapter.py   # Google Antigravity adapter (Gemini, Claude, transcript parsing)
├── codex_adapter.py         # OpenAI Codex / CLI / API adapter (GPT-4o, o1, etc.)
├── usage_monitor.py         # Threshold evaluation, deduplication, cooldowns
├── git_inspector.py         # Safe Git working tree, diff, and status inspection
├── checkpoint_generator.py  # Markdown projection adhering to Sections A-H
└── checkpoint_scheduler.py  # Orchestration, PostgreSQL persistence & Markdown sync
```

### Supported Native Adapters:
1. **Google Antigravity (`AntigravityAdapter`)**:
   - Model capacities: Gemini 1.5/2.0/2.5/3.8 Flash (1,048,576 tokens), Gemini 1.5 Pro (2,097,152 tokens), Claude 3.5/3.7/4.6 Sonnet (200,000 tokens), GPT-4o (128,000 tokens).
   - Ingests transcript token telemetry from `<appDataDir>/brain/<session-id>/.../transcript.jsonl` or in-flight tool calls.
   - Dispatches in-band warning levels (`info`, `urgent`, `critical`).
2. **OpenAI Codex (`CodexAdapter`)**:
   - Model capacities: GPT-4o (128,000 tokens), o1/o3-mini (200,000 tokens), GPT-4-turbo (128,000 tokens).
   - Ingests API usage envelopes (`prompt_tokens`, `completion_tokens`, `total_tokens`) and rate-limit headers.
3. **Extensible Adapters**:
   - Custom coding agents implement `BaseAgentAdapter` and register via `UsageMonitor.register_adapter(custom_adapter)`.

---

## 3. Telemetry Policy & Safe Limitations

Important rules enforced by the monitoring layer:
- **No Hallucinated Token Counts**: When an agent or environment does not expose token usage or context limits, metrics are strictly reported as `None` (unknown).
- **Quota Separation**: Account quotas (requests/min, monthly spend) are never conflated with active session context window capacity.
- **Graceful Fallbacks**: If context telemetry is unavailable, the system uses supported lifecycle events (e.g. `compaction_imminent`, `session_ending`) or configurable task-boundary/periodic checkpoints, clearly labeled as `fallback_periodic` or `fallback_task_boundary`.

---

## 4. Configurable Checkpoint Thresholds

Configured in `CheckpointPolicy`:

| Context Consumed | Action Taken | Trigger Reason |
|---|---|---|
| **70%** | Prepares lightweight checkpoint and sends informational warning to agent. | `threshold_70_prepare` |
| **80%** | **Automatically updates `checkpoint.md`** on disk and persists to PostgreSQL. | `threshold_80_auto` |
| **90%** | Triggers urgent checkpoint, syncs files, and warns agent to avoid large operations. | `threshold_90_urgent` |
| **95%** | Enters critical mode; immediate checkpoint written; halts expensive operations. | `threshold_95_critical` |

### Cooldown & Deduplication:
- A configurable `cooldown_seconds` (default: 60s) prevents thrashing when an agent remains above a threshold.
- Escalation to a higher severity (e.g., 80% $\to$ 90%) immediately bypasses the cooldown.
- Idempotency keys (`task_id:trigger_reason:version`) guarantee that duplicate requests are dropped safely.

---

## 5. Standard Structure of `checkpoint.md`

Every proactive update produces a `checkpoint.md` document conforming to 8 standard sections:

- **## A. Current Task**: Task ID, project name & ID, objective statement, active agent and session ID.
- **## B. Recent Changes**: Uncommitted files created, modified, deleted (via `git status --porcelain`), compact diff stat summary, touched project files.
- **## C. Completed Work**: Checklist of completed steps with evidence references, test execution results, applied verified fixes.
- **## D. Current Working State**: Active in-progress focus, last completed milestone, Git branch, latest commit hash, uncommitted changes count.
- **## E. Decisions and Reasoning**: Important technical decisions with rationale, rejected architectural alternatives.
- **## F. Known Problems**: Open bugs with symptoms and root causes, unresolved questions, blockers.
- **## G. Next Steps**: Sequenced pending steps and immediate next focus.
- **## H. Resumption Instructions**: Self-contained handover protocol enabling an independent AI agent to continue without conversation transcripts.

---

## 6. Execution Modes: Agent-Assisted vs Host-Side

Knowledge Brain supports two operational modes:

### Mode A: Agent-Assisted Checkpointing
The agent receives a threshold warning or milestone trigger, gathers its current execution state, and invokes the `task_checkpoint` MCP tool or REST endpoint.

### Mode B: Host-Side Checkpointing (Preferred)
The monitoring layer or App Server detects a context threshold crossing or lifecycle event (`compaction_imminent`) and triggers checkpoint generation **independently of the agent's turn**.
The scheduler recovers the latest known state from PostgreSQL, inspects the current Git working tree, and generates `checkpoint.md` even if the agent is blocked or crashes.

---

## 7. Storage, Synchronization & Conflict Handling

- **PostgreSQL is Canonical**: All versions are stored in `checkpoints` (`version`, `state_json`, `git_commit`, `git_branch`).
- **Markdown Projections**: `projects/<project_id>/checkpoint.md` is updated atomically using temporary file replacement.
- **Historical Preservation**: Past versions are kept in `projects/<project_id>/checkpoints/checkpoint_v{N}.md`.
- **Human Conflict Detection**: If a human developer manually edits `checkpoint.md` on disk, the synchronizer detects a SHA-256 hash mismatch against the database, sets document status to `conflict`, and preserves human edits rather than silently overwriting them.
- **Audit Logging**: Every trigger is recorded in the `checkpoint_triggers` table with percentage, tokens, version, and idempotency status.

---

## 8. API & MCP Tool Reference

### MCP Tools:
- **`agent_report_usage`**: Report agent context metrics, evaluate thresholds, and trigger checkpoints.
- **`agent_trigger_checkpoint`**: Explicitly trigger a proactive checkpoint and update `checkpoint.md`.
- **`task_checkpoint`**: Standard checkpoint tool with automatic `checkpoint.md` synchronization when `project_id` is supplied or linked.
- **`task_resume`**: Restore complete task context for an independent incoming agent.

### REST Endpoints:
- `POST /agent/usage`: Ingest usage telemetry, evaluate policy, and auto-checkpoint.
- `POST /agent/checkpoint/proactive`: Trigger immediate proactive checkpoint.
- `GET /agent/checkpoint/triggers/{task_id}`: Retrieve audit history of threshold events.

