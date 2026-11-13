# Knowledge Brain — System Architecture, Implemented Features & Storage Data Mapping

**File Name:** `KNOWLEDGE_BRAIN_FEATURES_AND_STORAGE.md`  
**Version:** 0.3.0  
**Verification Status:** 100% Implemented & Verified (102 / 102 Automated Tests Passing)  
**Repository Branch:** `knowledge-brain`

---

## 1. Executive Summary

**Knowledge Brain** is an enterprise-grade, persistent memory, project knowledge management, and dynamic evolution layer designed for autonomous AI agents and human development teams.

It bridges the gap between fast, multi-turn AI agent execution and long-term project context. By eliminating raw chat transcript dumping, Knowledge Brain organizes knowledge into three complementary pillars:
1. **Project Knowledge**: What the project is, its architectural patterns, technology stack, conventions, and active requirements (maintained as human-readable Markdown with PostgreSQL metadata).
2. **Operational Knowledge**: What agents have done, attempted, failed, fixed, and learned (stored as normalized relational records and versioned checkpoints).
3. **Evolution History**: How requirements, technical decisions, and database schemas evolve over time (stored as immutable versions, change proposals, approvals, and ADRs).

---

## 2. Storage Architecture & Data Storage Mapping

Knowledge Brain employs a **specialized multi-model storage architecture** where each storage engine handles the exact type of data it was optimized for. PostgreSQL remains the **sole authoritative source of truth**.

```
                                  +---------------------------------------+
                                  |     AI Agents / FastMCP / REST API    |
                                  +-------------------+-------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |          JEV Decision Engine          |
                                  |        (OpenRouter / Fallback)        |
                                  +-------------------+-------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |       Python Execution Layer          |
                                  |    (Validation, Pydantic, Outbox)     |
                                  +-------------------+-------------------+
                                                      |
        +-------------------------+-------------------+-------------------------+-------------------------+
        |                         |                                             |                         |
        v                         v                                             v                         v
+---------------+         +---------------+                             +---------------+         +---------------+
|  PostgreSQL   |         |   pgvector    |                             |     Redis     |         |     Neo4j     |
| (Authoritative|         | (Dense Vector |                             |  (In-Memory   |         | (Relationship |
| Source of TR) |         |  Embeddings)  |                             | Working Cache)|         |  Graph Index) |
+---------------+         +---------------+                             +---------------+         +---------------+
        |
        v
+---------------------------------------------------------------------------------------------------------+
|                                    Human-Readable Markdown Projections                                  |
|         projects/<project_id>/ (Architecture, Tech Stack, Requirements, ADRs, Changelog)                |
|         bug_knowledge/         (Defect Reports, Failed Attempt Traces, Verified Fix Evidence)           |
|         obsidian_vault/        (Bidirectional Wiki Links, Memory & Entity Notes)                        |
+---------------------------------------------------------------------------------------------------------+
```

---

### Detailed Storage Engines & Stored Data Types

| Storage Engine | Operational Role | Authoritative? | Specific Data Types & Entities Stored | Key Schema / Table References |
|---|---|---|---|---|
| **PostgreSQL 16** | **Authoritative Relational Core** | **YES (Source of Truth)** | • **Projects & Registry**: Project slugs, descriptions, repository URLs, document registries.<br>• **Requirements**: Stable IDs (`REQ-AUTH-001`), modules, categories, priorities.<br>• **Requirement Versions**: Immutable historical descriptions, acceptance criteria (`JSONB`), approval states.<br>• **Change Workflow**: Change requests, approval audit logs, blast-radius impacts.<br>• **Agent Tasks & Checkpoints**: Goal statements, completed/pending steps, decisions, rejected approaches, git commit/branch references, staleness flags.<br>• **Defects & Fixes**: Bugs, investigation attempts, empirical test verification proofs, append-only state transition events.<br>• **Memories & Provenance**: Persistent facts, procedures, epistemic states (`asserted`, `confirmed`), validity timestamps (`valid_from`, `valid_until`), superseding pointers (`supersedes_id`).<br>• **Audit & Telemetry**: Tool invocation logs (`call_log`), GDPR erasure receipts (`deletions`), JEV decision audit logs (`jev_decisions`), transactional outbox (`outbox_events`). | • `projects`<br>• `project_documents`<br>• `requirements`<br>• `requirement_versions`<br>• `change_requests`<br>• `change_approvals`<br>• `requirement_impacts`<br>• `tasks`<br>• `checkpoints`<br>• `bugs`<br>• `attempts`<br>• `fixes`<br>• `bug_events`<br>• `memories`<br>• `call_log`<br>• `deletions`<br>• `jev_decisions` |
| **PostgreSQL + pgvector** | **Semantic Vector Search Engine** | **NO (Derived Index)** | • **1536-Dimensional Dense Embeddings**: Vector representations of normalized memory claims, technical facts, and bug symptoms.<br>• **Similarity Indexing**: IVFFlat / HNSW indexes using Cosine Distance (`<=>`) for fuzzy, conceptual retrieval when keyword search fails. | • Vector column on `memories.embedding`<br>• `idx_memories_embedding` index |
| **Redis Stack Server** | **In-Memory Cache & Working Memory** | **NO (Temporary)** | • **Task Active Working State**: Live checkpoint drafts (`task:working:{task_id}`) with 24-hour TTL.<br>• **Intermediate Tool Outputs**: Scratchpad calculations, intermediate tool payloads, and raw API responses (`temp:*`) with short TTL (e.g. 1 hour).<br>• **Durable Safety Guarantee**: A durable checkpoint is **never** stored only in Redis; Redis acts strictly as an acceleration and crash-recovery layer. | • Key prefix `task:working:*`<br>• Key prefix `temp:*` |
| **Neo4j Graph Database** | **Relationship Graph & Multi-Hop Index** | **NO (Derived Index)** | • **Entity Nodes (`Entity`)**: Concept names, modules, services, tools.<br>• **Directed Edges / Predicates**: Explicit semantic relationships (`USES`, `DEPENDS_ON`, `CONFIGURED_WITH`, `EXTENDS`).<br>• **Traceability References**: Each edge contains `canonical_memory_id` and `epistemic_state`, mapping directly back to the authoritative PostgreSQL memory record. | • Node label `:Entity`<br>• Relationships: `[:PREDICATE {canonical_memory_id, epistemic_state}]` |
| **Project Markdown Base (`projects/`)** | **Human-Readable Project Knowledge** | **NO (Projected View)** | • **Project Metadata**: `PROJECT.md` (high-level vision, module breakdown).<br>• **Architecture Documents**: `system_architecture.md`, `database_design.md`, `infrastructure.md`.<br>• **Technical Guidelines**: `tech_stack.md`, `api_conventions.md`, `coding_standards.md`, `security.md`.<br>• **Requirement Specifications**: `requirements/<req_id>.md` and `requirements/index.md`.<br>• **Architecture Decision Records**: `decisions/ADR-001.md` and `decisions/index.md`.<br>• **Project Changelog**: `changelog.md` tracking all approved architectural and requirement upgrades. | Files located at `projects/<project_id>/` on disk |
| **Defect Knowledge Base (`bug_knowledge/`)** | **Human-Readable Defect Documentation** | **NO (Projected View)** | • **Bug Reports**: `bugs/BUG-<id>.md` (symptoms, root cause, chronological list of failed and successful investigation attempts).<br>• **Verified Fix Records**: `fixes/FIX-<id>.md` (code diff summary, test verification commands, exit codes).<br>• **Defect Dashboard**: `bug_knowledge/index.md` tracking open defects and regression statuses. | Files located at `bug_knowledge/` on disk |
| **Obsidian Vault (`obsidian_vault/`)** | **Interactive Visualization Graph** | **NO (Projected View)** | • **Obsidian Markdown Notes**: Wiki-linked notes (`[[Note Name]]`) for memories, project entities, and bugs, designed for exploration in Obsidian's visual Graph View. | Files located at `obsidian_vault/` on disk |

---

## 3. Comprehensive Feature Guide & Implementation Details

### Feature 1: Dynamic Project Evolution Intelligence
* **Canonical Requirements Management**: Supports defining requirements with stable IDs (`REQ-AUTH-001`), modules (`auth`, `billing`), categories (`functional`, `security`, `api`), and priorities (`low` to `critical`).
* **Immutable Versioning**: When requirements change, previous versions are preserved with their original acceptance criteria. New versions reference the superseded version.
* **Two-Step Approval Gate**:
  1. An agent or developer submits a proposal via `requirement_propose`. It is assigned status `proposed` and target version $N+1$. Current version $N$ remains active.
  2. A designated reviewer calls `requirement_approve`. On approval, version $N+1$ becomes active, version $N$ is marked `superseded`, and an approval audit record is written to `change_approvals`.
* **Automated Blast-Radius Impact Analysis**: Analyzes requirement descriptions against code modules, files, API endpoints, database tables, and test files (`requirement_impacts`).
* **Automated Task Staleness Synchronization**: When a requirement is approved, the system scans all active tasks targeting older versions and automatically flags them as `is_stale = TRUE`. When an agent resumes a stale task, it immediately receives a staleness warning alert and the updated requirement delta.

---

### Feature 2: Cross-Agent Task Resumption & Checkpointing
* **Durable Task Checkpoints**: AI agents save structured milestones using `task_checkpoint`. Every checkpoint records:
  - Completed steps with empirical evidence
  - In-progress and pending steps
  - Architectural decisions made with rationale
  - Explicit rejected options and why they were rejected
  - Open unresolved questions
  - Git commit hash, branch name, and dirty working tree status
* **Append-Only Concurrency Control**: Uses PostgreSQL row-level locks (`SELECT COALESCE(MAX(version), 0) + 1 FROM checkpoints WHERE task_id = %s FOR UPDATE;`) and optional `expected_version` checks to guarantee zero version collisions.
* **Zero-Transcript Resumption (`task_resume`)**: Enables a fresh agent (even from a different vendor, e.g. Claude $\to$ Gemini $\to$ GPT-4) to take over an unfinished task without transferring massive chat histories. Knowledge Brain extracts the actionable state, matching bug history, verified fixes, and current requirement versions within a controlled token budget.

---

### Feature 3: JEV Decision Engine Integration
* **Intelligent Gateway via OpenRouter**: Uses the Aura project's JEV decision engine over OpenRouter API (`google/gemini-2.5-flash`).
* **Strict Separation of Concerns**: JEV is the decision-making intelligence; Python is the execution and validation gatekeeper. JEV returns strict JSON validated by Pydantic; it is never permitted to execute raw SQL or bypass validation.
* **Bounded Operational Decisions**:
  - `decide_ingestion`: Determines category, importance, lifetime (`temporary` vs `persistent`), and multi-store targets.
  - `decide_retrieval`: Selects hybrid search strategy (semantic, keyword, graph) and filters candidates to fit token budgets.
  - `decide_handover`: Selects crucial technical context for resuming agents.
  - `decide_conflict`: Detects contradictions between claims (`supersede`, `dispute`, `coexist`, `reject`).
* **Graceful Deterministic Fallback**: If OpenRouter times out, experiences rate limits, or is disabled, the system automatically engages deterministic Python fallback logic without crashing.

---

### Feature 4: Defect Tracking & Empirical Verification Gates
* **Structured Defect Lifecycle**: Manages bugs through `open` $\to$ `investigating` $\to$ `fixed` $\to$ `verified` / `regressed`.
* **Failed Attempt Logging (`attempts`)**: Logs every debugging attempt (hypothesis, action, outcome, and traceback evidence). When future agents debug the task, they receive these logs so they never repeat dead-end approaches.
* **Empirical Verification Gate**: A bug can **never** be marked `verified` merely because an agent claims so. Verification strictly requires empirical test proof (passing test command and exit code `0`) or explicit human sign-off.
* **Duplicate & Regression Detection**: Matches error signatures against historical bugs. If an error matches a previously verified fix, it is automatically classified as a `regression_of`.

---

### Feature 5: Project Markdown Knowledge Base & Sync Engine
* **Automated Scaffolding**: Registering a project (`project_register`) automatically generates 9 standardized Markdown files on disk under `projects/<project_id>/`.
* **SHA-256 Hashing & Conflict Detection**: The sync engine computes content hashes before writing. If a human developer manually edits a document on disk, the synchronizer detects the hash mismatch and sets document status to `conflict` rather than silently overwriting human changes.
* **Atomic Writes**: Writes to temporary files before atomic file replacement to prevent file corruption during system interrupts.
* **Changelog Maintenance**: Meaningful project events (stack changes, requirement approvals, ADRs) automatically append chronological entries to `changelog.md`.
* **Task-Aware Project Context (`project_context`)**: Retrieves a compact, token-budgeted markdown brief (overview, tech stack, active requirements, ADRs, recent fixes) tailored for an agent working on a specific task.

---

### Feature 6: Provenance, Epistemic States & Verified Forgetting
* **Epistemic States**: Information is explicitly tagged as:
  - `asserted`: Agent-generated or unverified claims.
  - `confirmed`: Verified by automated tests or human approval.
  - `disputed`: Conflicting claims held for arbitration.
* **Verified Multi-Store Forgetting (`memory_forget`)**: When a memory or scope is deleted, the system coordinates erasure across PostgreSQL, pgvector, Redis, Neo4j, and Markdown projections, returning a signed deletion audit receipt (`deletions` table).

---

## 4. Complete Tool & API Reference

### FastMCP Tools (25 Registered Agent Tools)

| Category | Tool Name | Description | Key Arguments |
|---|---|---|---|
| **Project Knowledge** | `project_register` | Scaffolds and registers a new project knowledge base | `id`, `name`, `description`, `repository_url`, `root_path` |
| | `project_get` | Retrieves project metadata and status | `project_id` |
| | `project_context` | Task-aware project context retrieval with token budgeting | `project_id`, `task`, `token_budget` |
| | `project_documents_list` | Lists all registered documents and sync statuses | `project_id` |
| | `project_document_get` | Reads document content and PostgreSQL metadata | `project_id`, `relative_path` |
| | `project_document_sync` | Syncs Markdown content to disk and PostgreSQL | `project_id`, `relative_path`, `content`, `force` |
| | `project_document_validate`| Validates on-disk hash against DB recorded hash | `project_id`, `relative_path` |
| **Requirement Evolution** | `requirement_propose` | Proposes a new requirement or version upgrade | `req_id`, `title`, `description`, `proposed_description`, `project_id`, `module`, `priority`, `acceptance_criteria`, `reason` |
| | `requirement_approve` | Approves/rejects a proposal and marks tasks stale | `req_id`, `target_version`, `decision`, `approver`, `rationale` |
| | `requirement_get` | Retrieves current approved requirement specification | `req_id` |
| | `requirement_history` | Returns full immutable version history | `req_id` |
| | `requirement_impact` | Returns blast-radius impact analysis | `req_id`, `version` |
| | `requirement_check_staleness` | Checks if a task is stale against current requirements | `task_id` |
| **Task Resumption** | `task_checkpoint` | Saves persistent, versioned task state | `task_id`, `goal`, `steps`, `decisions`, `rejected`, `open_questions`, `written_by`, `project_files` |
| | `task_resume` | Resumes task with decisions, bugs, and staleness delta | `task_id`, `requesting_agent`, `token_budget` |
| **Memory & Epistemic** | `memory_search` | Hybrid semantic and keyword memory search | `query`, `token_budget`, `task_id` |
| | `memory_store` | Ingests factual knowledge with provenance | `content`, `type`, `source_actor` |
| | `memory_update` | Supersedes an existing memory record | `id`, `change`, `reason`, `agent` |
| | `memory_check_conflict`| Consults JEV to detect claim conflicts | `memory_id`, `new_claim`, `trust_level` |
| | `memory_forget` | Executes verified multi-store forgetting | `scope`, `agent` |
| **Defect Intelligence** | `bug_report` | Reports a new defect with location and signature | `bug_id`, `title`, `symptom`, `root_cause`, `severity`, `location`, `signature` |
| | `bug_log_attempt` | Logs failed/partial debugging attempt with evidence | `bug_id`, `agent`, `hypothesis`, `action`, `outcome`, `evidence`, `learned` |
| | `bug_record_fix` | Records fix with empirical test verification | `fix_id`, `bug_id`, `commit`, `files_changed`, `summary`, `verification`, `fixed_by` |
| | `bug_search` | Searches defects by file, symbol, or error string | `query` |
| | `bug_history` | Returns complete attempt, fix, and event history | `bug_id` |
| **Knowledge Graph** | `knowledge_graph_search`| Queries entity relationships in Neo4j | `query`, `task_id` |

---

### FastAPI REST Endpoints (20 HTTP Endpoints)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | System health check (PostgreSQL, Redis, Neo4j, JEV status) |
| `POST` | `/ingest` | Ingests raw text or conversation transcripts into memory |
| `POST` | `/search` | Searches memories with token budget constraints |
| `POST` | `/projects` | Registers a project and scaffolds Markdown documents |
| `GET` | `/projects/{project_id}` | Retrieves project metadata |
| `GET` | `/projects/{project_id}/documents` | Lists registered documents and sync states |
| `GET` | `/projects/{project_id}/context` | Returns task-aware project context |
| `POST` | `/requirements/create` | Creates a new canonical requirement |
| `POST` | `/requirements/propose` | Submits an unapproved version proposal |
| `POST` | `/requirements/{req_id}/approve` | Approves/rejects proposal and updates task staleness |
| `GET` | `/requirements/{req_id}` | Retrieves current approved requirement |
| `GET` | `/requirements/{req_id}/history` | Retrieves full requirement version history |
| `GET` | `/requirements/{req_id}/impact` | Retrieves blast-radius impact analysis |
| `POST` | `/tasks` | Initializes a new task record |
| `POST` | `/tasks/{task_id}/checkpoint` | Saves persistent checkpoint with version increment |
| `GET` | `/tasks/{task_id}/checkpoints` | Retrieves immutable checkpoint history |
| `GET` | `/tasks/{task_id}/status` | Retrieves current task owner and latest version |
| `GET` | `/tasks/{task_id}/resume` | Resumes task with handover context and staleness check |
| `GET` | `/tasks/{task_id}/staleness` | Checks task requirement staleness report |
| `POST` | `/tasks/{task_id}/associate_requirement` | Associates task with a specific requirement version |

---

## 5. Verification Test Suite (102 Tests Summary)

The test suite executes 102 comprehensive tests across 18 test modules:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-8.4.2
collected 102 items

• Defect & Markdown Sync (2 tests):
  - test_bug_and_failed_attempts_lifecycle: PASSED
  - test_markdown_projection_generation_and_regeneration: PASSED

• Checkpoint Persistence & Database (3 tests):
  - test_save_and_retrieve_checkpoint_versions: PASSED
  - test_concurrency_detection: PASSED
  - test_resume_service_with_bugs_and_fixes: PASSED

• Checkpoint & Resume Integration (3 tests):
  - test_task_checkpoint_versioning: PASSED
  - test_resume_without_redis_and_without_transcript: PASSED
  - test_invalid_checkpoint_rejected: PASSED

• Core Infrastructure (4 tests):
  - test_postgres_connection_and_pgvector: PASSED
  - test_postgres_canonical_tables_exist: PASSED
  - test_redis_connection_and_ttl: PASSED
  - test_neo4j_connection_and_cypher: PASSED

• Ingestion API (4 tests):
  - test_health_check_endpoint: PASSED
  - test_ingest_conversation_creates_source_and_memories: PASSED
  - test_ingest_planted_claim_remains_asserted: PASSED
  - test_ingest_rejects_malformed_payload: PASSED

• JEV Decision Engine (5 tests):
  - test_jev_decide_ingestion_and_audit_logging: PASSED
  - test_jev_decide_retrieval: PASSED
  - test_jev_decide_handover: PASSED
  - test_jev_decide_conflict: PASSED
  - test_jev_graceful_fallback_when_disabled: PASSED

• Project Evolution & Markdown Synchronization (7 tests):
  - test_1_new_project_registration: PASSED
  - test_2_technology_stack_update_and_changelog: PASSED
  - test_3_requirement_evolution_proposal_and_approval: PASSED
  - test_4_architecture_decision_adr: PASSED
  - test_5_agent_handover_with_staleness_warning: PASSED
  - test_6_manual_markdown_change_conflict_detection: PASSED
  - test_7_project_isolation: PASSED

• Project Evolution API & FastMCP Tools (2 tests):
  - test_project_and_requirement_rest_api_lifecycle: PASSED
  - test_mcp_project_and_evolution_tools: PASSED

• Retrieval Pipeline (4 tests):
  - test_semantic_retrieval_with_provenance_and_ranking: PASSED
  - test_graph_relationship_retrieval: PASSED
  - test_matching_bug_history_included: PASSED
  - test_abstention_on_unknown_query: PASSED

• Multi-Store Routing & Outbox (4 tests):
  - test_redis_temporary_routing: PASSED
  - test_postgres_pgvector_routing_and_search: PASSED
  - test_neo4j_graph_synchronization_with_pg_reference: PASSED
  - test_outbox_retry_idempotence: PASSED

• Verified Forgetting (2 tests):
  - test_verified_forgetting_multi_store_erasure: PASSED
  - test_forgetting_by_text_scope: PASSED

• Cross-Agent Scenarios & Benchmark (5 tests):
  - test_cross_agent_benchmark_execution: PASSED
  - test_cross_agent_handover_scenario: PASSED
  - test_crud_lifecycle_task_api: PASSED
  - test_validation_error_handling: PASSED
  - test_thirty_session_scenario: PASSED

• Unit Tests (57 tests):
  - test_checkpoints (5 tests): PASSED
  - test_checkpoint_schema (4 tests): PASSED
  - test_bug_verification_gate (2 tests): PASSED
  - test_jev_contracts (8 tests): PASSED
  - test_jev_client (7 tests): PASSED
  - test_provenance_rules (4 tests): PASSED
  - test_retrieval_budget (3 tests): PASSED
  - test_router (3 tests): PASSED
  - test_schemas (6 tests): PASSED
  - test_obsidian_export (4 tests): PASSED
  - test_forget_receipt (2 tests): PASSED
  - test_mcp_server & validation (9 tests): PASSED

======================= 102 passed in 242.22s (0:04:02) =======================
```

---

## 6. How Developers and AI Agents Use Knowledge Brain

### In Antigravity Agent Chat
Because Knowledge Brain is configured in Antigravity's `mcp_config.json`, agents automatically invoke tools via natural language or `@`-mentions:

```markdown
# 1. Starting or Resuming a Task:
"Resume task AUTH-001 using Knowledge Brain. What steps are done and what requirement version am I targeting?"

# 2. Saving a Progress Checkpoint:
"Save a checkpoint for task AUTH-001: User registration and password hashing are complete. JWT refresh token rotation is pending."

# 3. Proposing an Upstream Requirement Change:
"Propose an update to requirement REQ-AUTH-001: Add support for OAuth2 Google and GitHub SSO with automatic user provisioning."

# 4. Reviewing and Approving Requirements:
"Approve version 2 of requirement REQ-AUTH-001. Rationale: Approved for Q4 SSO milestone."

# 5. Fetching Project Context:
"Fetch project context for 'ecommerce' focused on task 'Implement Stripe Checkout'."
```

### In Terminal / CLI
```bash
# Start background services
docker compose up -d

# Start the FastMCP agent server over stdio
python mcp_server.py

# Start the FastAPI REST server with interactive Swagger docs
python api.py
# Open: http://localhost:8000/docs

# Run the complete automated test suite
pytest -v
```

