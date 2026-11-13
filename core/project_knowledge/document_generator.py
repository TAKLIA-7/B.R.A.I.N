from typing import Dict, Any, List, Optional
from datetime import datetime

class ProjectDocumentGenerator:
    """Generates verified, human-readable Markdown templates for projects."""

    @staticmethod
    def generate_project_md(project: Dict[str, Any]) -> str:
        pid = project["id"]
        name = project["name"]
        desc = project.get("description") or "Persistent Knowledge Base Project"
        repo = project.get("repository_url") or "Not registered"

        return f"""# {name} (`{pid}`)

## Project Overview
{desc}

- **Repository**: {repo}
- **Status**: {project.get('status', 'active')}
- **Initialized**: {datetime.now().strftime('%Y-%m-%d')}

## Navigation
- [System Architecture](architecture/system_architecture.md)
- [Database Design](architecture/database_design.md)
- [Infrastructure](architecture/infrastructure.md)
- [Technology Stack](technical/tech_stack.md)
- [API Conventions](technical/api_conventions.md)
- [Coding Standards](technical/coding_standards.md)
- [Security Guidelines](technical/security.md)
- [Active Requirements](requirements/index.md)
- [Architecture Decisions (ADRs)](decisions/index.md)
- [Changelog](changelog.md)
"""

    @staticmethod
    def generate_changelog_md(project_name: str) -> str:
        today = datetime.now().strftime('%Y-%m-%d')
        return f"""# {project_name} Changelog

All notable technical and architectural changes to this project are documented here.

## [{today}] - Project Knowledge Initialized
- Initialized project knowledge structure.
- Registered canonical architecture, tech stack, and conventions documents.
"""

    @staticmethod
    def generate_system_architecture_md(project_name: str) -> str:
        return f"""# System Architecture: {project_name}

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
"""

    @staticmethod
    def generate_database_design_md(project_name: str) -> str:
        return f"""# Database Design: {project_name}

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
"""

    @staticmethod
    def generate_infrastructure_md(project_name: str) -> str:
        return f"""# Infrastructure & Deployment: {project_name}

## 1. Environment & Containers
- Multi-container architecture managed via Docker Compose:
  - `postgres`: PostgreSQL 16 with `pgvector/pgvector:pg16` on port 5432.
  - `redis`: Redis Stack Server on port 6379.
  - `neo4j`: Neo4j Community on ports 7474 (HTTP) and 7687 (Bolt).

## 2. Security & Credentials
- All sensitive database passwords, OpenRouter API keys, and secret tokens are loaded via environment variables (`.env`).
- Never check raw production credentials into Git or Markdown files.
"""

    @staticmethod
    def generate_tech_stack_md(project_name: str, tech_stack: Optional[Dict[str, Any]] = None) -> str:
        ts = tech_stack or {
            "Language": "Python 3.11+",
            "API Framework": "FastAPI, FastMCP",
            "Data Validation": "Pydantic v2",
            "Databases": "PostgreSQL 16, pgvector, Redis, Neo4j",
            "Testing": "pytest, pytest-asyncio",
            "LLM Gateway": "OpenRouter (JEV Decision Engine)"
        }
        lines = [
            f"# Technology Stack: {project_name}",
            "",
            "## Core Technologies & Dependencies",
            ""
        ]
        for k, v in ts.items():
            lines.append(f"- **{k}**: {v}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def generate_api_conventions_md(project_name: str) -> str:
        return f"""# API Conventions: {project_name}

## 1. Design & Protocol
- REST endpoints adhere to OpenAPI 3.1 specifications via FastAPI.
- Agent tools follow FastMCP (Model Context Protocol) conventions.

## 2. Response & Error Formats
- Success responses return JSON objects with descriptive keys.
- Error responses return HTTP standard error codes with structured `detail` messages.
"""

    @staticmethod
    def generate_coding_standards_md(project_name: str) -> str:
        return f"""# Coding Standards & Guidelines: {project_name}

## 1. Code Style
- Adhere to PEP 8 standards with strict type hinting.
- Use strict Pydantic v2 schemas (`extra='forbid'` where inputs must be constrained).

## 2. Testing & Verification Gate
- Code changes must be covered by automated tests (`pytest`).
- Fixes for defects cannot be marked verified without passing test proof.
"""

    @staticmethod
    def generate_security_md(project_name: str) -> str:
        return f"""# Security Policy & Conventions: {project_name}

## 1. Authentication & Secret Management
- API Keys and JWT signing secrets must be managed through `.env`.
- No raw secrets in version control or generated Markdown files.

## 2. SQL & Query Security
- All database operations must use parameterized queries (`%s` placeholders).
- Never use direct string interpolation for database queries.
"""

    @staticmethod
    def generate_requirement_md(req: Dict[str, Any], versions: List[Dict[str, Any]]) -> str:
        req_id = req["req_id"]
        title = req["title"]
        category = req.get("category", "functional")
        priority = req.get("priority", "medium")
        status = req.get("status", "approved")
        current_v = req.get("current_version", 1)

        lines = [
            "---",
            f"req_id: {req_id}",
            f"title: \"{title}\"",
            f"module: {req.get('module', 'general')}",
            f"category: {category}",
            f"priority: {priority}",
            f"current_version: {current_v}",
            f"status: {status}",
            "---",
            "",
            f"# {req_id}: {title}",
            "",
            f"**Current Status**: `{status}` | **Priority**: `{priority}` | **Current Version**: `v{current_v}`",
            "",
            "## Current Specification",
            req.get("current_description", "No description provided."),
            "",
            "## Acceptance Criteria",
        ]
        criteria = req.get("acceptance_criteria") or []
        if criteria:
            for c in criteria:
                lines.append(f"- [ ] {c}")
        else:
            lines.append("- [ ] None specified.")

        lines.extend(["", "## Version History", ""])
        for v in versions:
            v_num = v["version"]
            v_status = v.get("approval_status", "proposed")
            v_author = v.get("created_by", "unknown")
            v_approver = v.get("approved_by") or "None"
            lines.append(f"### Version {v_num} (`{v_status}`)")
            lines.append(f"- **Author**: {v_author}")
            lines.append(f"- **Approved By**: {v_approver}")
            lines.append(f"- **Description**: {v.get('description', '')}")
            lines.append("")

        return "\n".join(lines)

