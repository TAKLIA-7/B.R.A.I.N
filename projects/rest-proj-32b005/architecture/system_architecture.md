# System Architecture: Cloud Platform

## 1. High-Level Architecture
- Architecture Pattern: Modular Service Architecture / Event-Driven Persistence.
- Core Layers:
  1. AI Agents & External Clients (FastMCP / REST)
  2. Orchestration & Decision Layer (JEV Decision Engine)
  3. Deterministic Python Execution & Validation Layer
  4. Authoritative Relational Persistence (PostgreSQL + pgvector)
  5. Temporary State & Working Memory (Redis)
  6. Graph Relationships (Neo4j)
  7. Human-Readable Knowledge Projections (Markdown)

## 2. Communication & Data Flow
- Standardized tool calls via FastMCP over stdio.
- Asynchronous and retryable projection syncing via transactional outbox.
