import os
import json
import logging
from typing import Dict, Any, List, Optional
from core.adapters.postgres import PostgresAdapter
from core.retrieve.context_budget import ContextBudgetManager
from core.project_knowledge.schemas import (
    ProjectCreateRequest,
    ProjectItem,
    ProjectDocumentItem,
    DocumentSyncResult,
    ProjectContextResponse
)
from core.project_knowledge.document_generator import ProjectDocumentGenerator
from core.project_knowledge.synchronizer import ProjectDocumentSynchronizer

logger = logging.getLogger(__name__)

class ProjectKnowledgeManager:
    """
    Central orchestrator for project registration, Markdown document lifecycle,
    automatic synchronization, and task-aware context retrieval (Phase 5).
    """

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        synchronizer: Optional[ProjectDocumentSynchronizer] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.sync = synchronizer or ProjectDocumentSynchronizer(postgres_adapter=self.pg)
        self.generator = ProjectDocumentGenerator()
        self.budget_manager = ContextBudgetManager()

    def register_project(self, req: ProjectCreateRequest) -> ProjectItem:
        """
        Registers a new project, scaffolds its dedicated Markdown knowledge base,
        and synchronizes all documents with PostgreSQL.
        """
        # 1. Upsert project in PostgreSQL
        sql = """
            INSERT INTO projects (id, name, description, repository_url, root_path, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 'active', NOW(), NOW())
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                repository_url = EXCLUDED.repository_url,
                root_path = EXCLUDED.root_path,
                updated_at = NOW()
            RETURNING id, name, description, repository_url, root_path, status, created_at, updated_at;
        """
        rows = self.pg.execute_query(sql, (req.id, req.name, req.description, req.repository_url, req.root_path))
        p = rows[0]

        # 2. Scaffold initial documents
        initial_docs = [
            ("PROJECT.md", "project", self.generator.generate_project_md(p)),
            ("changelog.md", "changelog", self.generator.generate_changelog_md(req.name)),
            ("architecture/system_architecture.md", "architecture", self.generator.generate_system_architecture_md(req.name)),
            ("architecture/database_design.md", "database", self.generator.generate_database_design_md(req.name)),
            ("architecture/infrastructure.md", "infrastructure", self.generator.generate_infrastructure_md(req.name)),
            ("technical/tech_stack.md", "tech_stack", self.generator.generate_tech_stack_md(req.name)),
            ("technical/api_conventions.md", "api_conventions", self.generator.generate_api_conventions_md(req.name)),
            ("technical/coding_standards.md", "coding_standards", self.generator.generate_coding_standards_md(req.name)),
            ("technical/security.md", "security", self.generator.generate_security_md(req.name)),
            ("requirements/index.md", "requirement_index", f"# Active Requirements: {req.name}\n\nNo requirements registered yet.\n"),
            ("decisions/index.md", "decision_index", f"# Architecture Decision Records: {req.name}\n\nNo ADRs recorded yet.\n")
        ]

        # 3. Synchronize all initial documents
        for rel_path, doc_type, content in initial_docs:
            self.sync.sync_document(req.id, rel_path, doc_type, content, force=True)

        return ProjectItem(
            id=p["id"],
            name=p["name"],
            description=p.get("description"),
            repository_url=p.get("repository_url"),
            root_path=p.get("root_path"),
            status=p["status"],
            created_at=str(p["created_at"]),
            updated_at=str(p["updated_at"])
        )

    def get_project(self, project_id: str) -> Optional[ProjectItem]:
        """Fetches project record from PostgreSQL."""
        rows = self.pg.execute_query("SELECT * FROM projects WHERE id = %s;", (project_id,))
        if not rows:
            return None
        p = rows[0]
        return ProjectItem(
            id=p["id"],
            name=p["name"],
            description=p.get("description"),
            repository_url=p.get("repository_url"),
            root_path=p.get("root_path"),
            status=p["status"],
            created_at=str(p["created_at"]),
            updated_at=str(p["updated_at"])
        )

    def list_documents(self, project_id: str) -> List[ProjectDocumentItem]:
        """Lists all registered documents and their synchronization state."""
        rows = self.pg.execute_query(
            "SELECT * FROM project_documents WHERE project_id = %s ORDER BY relative_path ASC;",
            (project_id,)
        )
        return [
            ProjectDocumentItem(
                id=str(r["id"]),
                project_id=r["project_id"],
                document_type=r["document_type"],
                relative_path=r["relative_path"],
                version=r["version"],
                content_hash=r["content_hash"],
                status=r["status"],
                last_synced_at=str(r["last_synced_at"])
            )
            for r in rows
        ]

    def get_document(self, project_id: str, relative_path: str) -> Optional[Dict[str, Any]]:
        """Returns document content from disk along with metadata from PostgreSQL."""
        rows = self.pg.execute_query(
            "SELECT * FROM project_documents WHERE project_id = %s AND relative_path = %s;",
            (project_id, relative_path)
        )
        if not rows:
            return None

        doc = rows[0]
        pdir = self.sync.get_project_dir(project_id)
        abs_path = os.path.join(pdir, relative_path)
        content = self.sync.read_file(abs_path)

        return {
            "project_id": project_id,
            "relative_path": relative_path,
            "document_type": doc["document_type"],
            "version": doc["version"],
            "content_hash": doc["content_hash"],
            "status": doc["status"],
            "content": content
        }

    def update_tech_stack(
        self,
        project_id: str,
        tech_stack: Dict[str, Any],
        author: str = "architect"
    ) -> bool:
        """Updates tech_stack.md and records a changelog entry."""
        p = self.get_project(project_id)
        pname = p.name if p else project_id
        content = self.generator.generate_tech_stack_md(pname, tech_stack)
        success, status = self.sync.sync_document(project_id, "technical/tech_stack.md", "tech_stack", content, force=True)
        if success:
            self.sync.append_changelog(project_id, "technology stack", "Updated technology stack definition", author)
        return success

    def sync_requirement_doc(
        self,
        project_id: str,
        req_id: str,
        req_data: Dict[str, Any],
        versions_data: List[Dict[str, Any]]
    ) -> bool:
        """Generates/updates Markdown file for a requirement and updates requirements/index.md."""
        content = self.generator.generate_requirement_md(req_data, versions_data)
        rel_path = f"requirements/{req_id}.md"
        success, _ = self.sync.sync_document(project_id, rel_path, "requirement", content, force=True)

        # Update requirements/index.md
        index_rows = self.pg.execute_query(
            "SELECT req_id, title, status, priority, current_version FROM requirements WHERE project_id = %s OR project_id IS NULL ORDER BY req_id ASC;",
            (project_id,)
        )
        lines = [f"# Active Requirements: {project_id}\n"]
        for r in index_rows:
            lines.append(f"- [{r['req_id']}: {r['title']}]({r['req_id']}.md) (v{r['current_version']}, `{r['status']}`)")
        index_content = "\n".join(lines) + "\n"
        self.sync.sync_document(project_id, "requirements/index.md", "requirement_index", index_content, force=True)

        # Append to changelog
        self.sync.append_changelog(
            project_id, "requirement",
            f"Synchronized requirement {req_id} v{req_data.get('current_version', 1)}",
            req_data.get("created_by", "system")
        )
        return success

    def record_decision_adr(
        self,
        project_id: str,
        decision_id: str,
        title: str,
        context: str,
        decision: str,
        consequences: str,
        author: str = "architect",
        supersedes: Optional[str] = None
    ) -> str:
        """Creates an Architecture Decision Record (ADR) and updates decisions/index.md."""
        adr_content = f"""# {decision_id}: {title}

- **Status**: Approved
- **Author**: {author}
- **Supersedes**: {supersedes or 'None'}

## Context
{context}

## Decision
{decision}

## Consequences
{consequences}
"""
        rel_path = f"decisions/{decision_id}.md"
        self.sync.sync_document(project_id, rel_path, "decision", adr_content, force=True)

        # Update decisions/index.md
        pdir = self.sync.get_project_dir(project_id)
        index_path = os.path.join(pdir, "decisions/index.md")
        cur_index = self.sync.read_file(index_path) or f"# Architecture Decisions: {project_id}\n\n"
        entry = f"- [{decision_id}: {title}]({decision_id}.md) - {decision[:60]}...\n"
        self.sync.sync_document(project_id, "decisions/index.md", "decision_index", cur_index + entry, force=True)

        self.sync.append_changelog(project_id, "architecture", f"Approved ADR {decision_id}: {title}", author)
        return rel_path

    def get_project_context(
        self,
        project_id: str,
        task: Optional[str] = None,
        token_budget: int = 4000
    ) -> ProjectContextResponse:
        """
        Phase 5: Task-aware project knowledge retrieval.
        Assembles project overview, active requirements, tech stack, and relevant ADRs
        within the requested token budget without conversational transcripts.
        """
        p = self.get_project(project_id)
        pname = p.name if p else project_id

        # 1. Read key documents
        overview_doc = self.get_document(project_id, "PROJECT.md")
        overview = overview_doc.get("content", "") if overview_doc else ""

        arch_doc = self.get_document(project_id, "architecture/system_architecture.md")
        arch = arch_doc.get("content", "") if arch_doc else ""

        tech_doc = self.get_document(project_id, "technical/tech_stack.md")
        tech = tech_doc.get("content", "") if tech_doc else ""

        # 2. Fetch approved requirements from PostgreSQL
        req_rows = self.pg.execute_query(
            "SELECT req_id, title, category, priority, current_version, status FROM requirements WHERE (project_id = %s OR project_id IS NULL) AND status = 'approved' ORDER BY current_version DESC LIMIT 5;",
            (project_id,)
        )

        # 3. Fetch recent bug fixes
        fix_rows = self.pg.execute_query(
            "SELECT fix_id, bug_id, summary, fixed_by FROM fixes ORDER BY created_at DESC LIMIT 3;"
        )

        # 4. Format context text
        context_lines = [
            f"# Project Context: {pname} (`{project_id}`)",
            f"**Task Focus**: {task or 'General Development'}",
            "",
            "## 1. Project Summary",
            overview[:600] if overview else "No project overview available.",
            "",
            "## 2. Core Architecture & Tech Stack",
            tech[:500] if tech else "Python 3.11+, FastAPI, PostgreSQL, Redis",
            "",
            "## 3. Active Approved Requirements"
        ]
        if req_rows:
            for r in req_rows:
                context_lines.append(f"- **{r['req_id']}** (v{r['current_version']}): {r['title']} [Priority: `{r['priority']}`]")
        else:
            context_lines.append("- No requirements formally registered.")

        if fix_rows:
            context_lines.extend(["", "## 4. Recent Verified Fixes"])
            for f in fix_rows:
                context_lines.append(f"- **{f['fix_id']}** ({f['bug_id']}): {f['summary']}")

        full_context = "\n".join(context_lines)
        tokens_est, _ = self.budget_manager.estimate_tokens(full_context)

        return ProjectContextResponse(
            project_id=project_id,
            project_name=pname,
            task_focus=task,
            project_overview=overview,
            architecture=arch,
            tech_stack=tech,
            active_requirements=req_rows,
            decisions=[],
            related_bugs=fix_rows,
            context_markdown=full_context,
            token_budget=token_budget,
            estimated_tokens=tokens_est
        )

