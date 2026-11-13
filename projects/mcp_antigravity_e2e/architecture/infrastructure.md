# Infrastructure & Deployment: Antigravity E2E MCP Project

## 1. Environment & Containers
- Multi-container architecture managed via Docker Compose:
  - `postgres`: PostgreSQL 16 with `pgvector/pgvector:pg16` on port 5432.
  - `redis`: Redis Stack Server on port 6379.
  - `neo4j`: Neo4j Community on ports 7474 (HTTP) and 7687 (Bolt).

## 2. Security & Credentials
- All sensitive database passwords, OpenRouter API keys, and secret tokens are loaded via environment variables (`.env`).
- Never check raw production credentials into Git or Markdown files.
