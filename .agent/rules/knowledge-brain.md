# Knowledge Brain Invariant Rules

1. Stack: Python, FastAPI, FastMCP, PostgreSQL + pgvector, Redis and Neo4j; Obsidian optional.
2. All business logic lives in `core/`.
3. PostgreSQL is the source of truth.
4. Redis is temporary and uses TTL; durable checkpoints belong in PostgreSQL.
5. pgvector is the semantic index inside PostgreSQL.
6. Neo4j is a derived relationship index referencing canonical PostgreSQL IDs.
7. Obsidian Markdown is a human-readable projection, never the source of truth.
8. Bug/fix Markdown files are generated from structured PostgreSQL records.
9. History and bug events are append-only.
10. Agent claims default to asserted; confirmation requires evidence or approval.
11. Every memory preserves source and writing agent.
12. Retrieval honors token budgets and abstains when evidence is weak.
13. Validate writes with strict schemas and return clear errors.
14. Derived-index synchronization is retryable and idempotent.
15. Deletion covers derived stores and verifies non-retrieval.
16. Respect non-goals and phase order in `SPEC.md`.

