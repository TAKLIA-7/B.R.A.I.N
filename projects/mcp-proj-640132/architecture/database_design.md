# Database Design: FastMCP Service

## 1. Database Technologies
- **Primary Relational Store**: PostgreSQL (ACID transactions, row-level locking, foreign keys).
- **Vector Search Engine**: PostgreSQL with `pgvector` extension (HNSW / IVFFlat, cosine distance).
- **Cache & Temporary State**: Redis (Working memory, TTL keys).
- **Knowledge Graph**: Neo4j (Entity relationships, graph traversal).

## 2. Canonical Entities
- `projects`: Registered workspaces and repositories.
- `project_documents`: Synchronized project Markdown metadata and hashes.
- `requirements` & `requirement_versions`: Immutable requirement progression.
- `memories`: Epistemic asserted/confirmed facts, decisions, and procedures.
- `tasks` & `checkpoints`: Durable agent milestones with versioning and staleness tracking.
- `bugs`, `attempts`, `fixes`: Defect investigation logs and test verification records.
