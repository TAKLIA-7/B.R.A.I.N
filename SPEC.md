# Knowledge Brain --- System Specification (SPEC.md)

## 1. System Overview
Knowledge Brain is a persistent memory layer for AI agents, providing durable long-term memory, cross-agent session portability, deterministic storage routing, structured bug tracking, and verified forgetting.

## 2. Storage Architecture and Responsibilities
Knowledge Brain uses a tiered storage hierarchy with strict ownership boundaries:

### PostgreSQL (Canonical Store & Source of Truth)
- Owns all authoritative records: memories, provenance (`sources`), tasks, checkpoints, deletions, call logs, and structured bug tracking (`bugs`, `attempts`, `fixes`, `bug_events`).
- Embedded pgvector (`vector` extension) handles semantic vector retrieval directly inside PostgreSQL.
- Derived stores (Neo4j, Redis, Obsidian) synchronize from PostgreSQL via transactional outbox patterns. If conflicts arise, PostgreSQL is always the authoritative source of truth.

### Redis (Temporary Context & Working State)
- Handles short-lived conversation history, working agent context, intermediate tool outputs, and query caches.
- All session records enforce a strict Time-to-Live (TTL).
- Redis is never the sole repository for resumable or critical task checkpoints. Service restarts or Redis eviction must never cause data loss for durable tasks.

### Neo4j (Derived Knowledge Graph)
- Traverses entity-relationship networks (e.g., `User`, `Project`, `Technology`, `Decision`, `Task`, `Document`, `Source`, `Memory`/`Claim`).
- Every graph node/relationship referencing a memory points to the canonical PostgreSQL memory UUID.
- Unverified/asserted claims in the graph are explicitly labeled and never treated as confirmed facts.

### Obsidian (Human-Facing Projections)
- Read-only human projection in Markdown format (`bug_knowledge/` and optional notes).
- Projections are generated idempotently from PostgreSQL. Markdown files are never the canonical record.

## 3. Canonical Database Schema
- `sources`: Tracks data origin, actor/author, trust level, and creation timestamp.
- `memories`: Core assertions and observations (`active | superseded | deleted`), epistemic states (`asserted | confirmed | disputed`), source links, temporal validity, and vector embeddings.
- `tasks`: High-level agent goals and metadata.
- `checkpoints`: Versioned, immutable task execution checkpoints containing serialized state.
- `call_log`: Telemetry for every MCP tool invocation (agent, tool, latency, token metrics).
- `deletions`: Verifiable audit receipts for forgotten memory scopes.
- `bugs`: Structured defects with location, signature, status, severity, and epistemic state.
- `attempts`: Failed, partial, or successful investigation steps.
- `fixes`: Verified code changes, links to commits, and explicit verification test outputs.
- `bug_events`: Append-only transition history for bugs.
- `outbox_events`: Queue for idempotent, retryable synchronization to derived stores (Neo4j, pgvector).

## 4. Non-Goals
- No custom user authentication or multi-tenant management systems.
- No third-party standalone vector databases (e.g., Qdrant, Pinecone). pgvector is the only vector store.
- No distributed message brokers (e.g., Kafka).
- No direct database writes from LLM outputs without deterministic application validation.

