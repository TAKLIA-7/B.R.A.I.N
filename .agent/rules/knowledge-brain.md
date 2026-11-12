# Knowledge Brain Invariant Rules

1. Architecture: AI Agents -> FastMCP / REST -> Knowledge Brain Core -> JEV Decision Engine -> Python Execution Layer -> Storage Systems.
2. JEV is the central decision-making and orchestration layer.
3. OpenRouter provides model access and inference capabilities to JEV.
4. Python strictly validates (Pydantic, referential integrity) and executes JEV decisions. JEV must never execute arbitrary database queries or bypass application validation.
5. PostgreSQL is the authoritative canonical source of truth for memories, provenance, tasks, checkpoints, deletions, bugs, and JEV decision audit records.
6. pgvector is the semantic index within PostgreSQL using cosine distance.
7. Redis stores temporary context and active working state with enforced TTL; durable checkpoints belong in PostgreSQL.
8. Neo4j is a derived relationship index referencing canonical PostgreSQL IDs.
9. Obsidian Markdown is an optional human-readable projection, never the source of truth.
10. Bug/fix Markdown files are generated from structured PostgreSQL records with verification gates.
11. History, bug events, and JEV decision audit logs are append-only.
12. Agent-generated claims default to asserted; confirmed knowledge requires test evidence or explicit human approval.
13. Every memory preserves source provenance, author, and writing agent.
14. Retrieval honors token budgets and abstains with 'no supporting memory' when evidence is weak.
15. Memory deletion covers all derived stores (pgvector, Redis, Neo4j, Markdown) and produces verifiable receipts.
16. Derived-index synchronization is retryable, idempotent, and non-blocking via transactional outbox.

## Checkpoint and Cross-Agent Resumption Invariants

17. Never start a task without checking for existing checkpoints (`task_resume`).
18. Always resume from the latest checkpoint.
19. Save a checkpoint after every meaningful milestone (`task_checkpoint`).
20. Never pass raw conversational history to resuming agents.
21. Record failed attempts as explicit rejected approaches or bug attempts.
22. Verify fixes before marking steps complete.
23. Record git commit and branch whenever available; report uncommitted working tree if dirty.
24. Update task ownership upon resuming.
25. Checkpoints are strictly append-only in PostgreSQL; never overwrite existing versions.
26. Concurrency control uses row-level locking (`SELECT FOR UPDATE`) and expected version checks to prevent race conditions.
