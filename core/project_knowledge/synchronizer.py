import os
import hashlib
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple
from core.adapters.postgres import PostgresAdapter

logger = logging.getLogger(__name__)

class ProjectDocumentSynchronizer:
    """
    Manages synchronization between PostgreSQL metadata and project Markdown files.
    Enforces atomic writes, SHA-256 content hashing, idempotency, and conflict detection.
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        postgres_adapter: Optional[PostgresAdapter] = None
    ):
        if base_dir is None:
            # Default to repo root / projects
            current_dir = os.path.dirname(os.path.abspath(__file__))
            base_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "projects"))
        self.base_dir = base_dir
        self.pg = postgres_adapter or PostgresAdapter()
        os.makedirs(self.base_dir, exist_ok=True)

    def get_project_dir(self, project_id: str) -> str:
        pdir = os.path.join(self.base_dir, project_id)
        os.makedirs(pdir, exist_ok=True)
        return pdir

    @staticmethod
    def compute_hash(content: str) -> str:
        """Computes SHA-256 hash of text content."""
        return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()

    def write_atomic(self, file_path: str, content: str) -> None:
        """Atomically writes content to disk using a temporary file."""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        tmp_path = f"{file_path}.tmp.{uuid.uuid4().hex[:6]}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        # Atomic replace
        os.replace(tmp_path, file_path)

    def read_file(self, file_path: str) -> Optional[str]:
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def sync_document(
        self,
        project_id: str,
        relative_path: str,
        document_type: str,
        content: str,
        force: bool = False
    ) -> Tuple[bool, str]:
        """
        Syncs a single Markdown document to disk and updates PostgreSQL.
        Detects if a human made manual changes to prevent silent overwrites unless forced.
        """
        pdir = self.get_project_dir(project_id)
        abs_path = os.path.join(pdir, relative_path)
        new_hash = self.compute_hash(content)

        # 1. Query existing document record in PostgreSQL
        sql = """
            SELECT id, version, content_hash, status
            FROM project_documents
            WHERE project_id = %s AND relative_path = %s;
        """
        rows = self.pg.execute_query(sql, (project_id, relative_path))
        doc_record = rows[0] if rows else None

        # 2. Check for manual on-disk changes if file exists
        if os.path.exists(abs_path) and doc_record and not force:
            disk_content = self.read_file(abs_path)
            if disk_content is not None:
                disk_hash = self.compute_hash(disk_content)
                # If disk hash differs from DB recorded hash, user edited it manually!
                if disk_hash != doc_record["content_hash"] and disk_hash != new_hash:
                    logger.warning(f"Conflict detected for {relative_path} in {project_id}: manual edits on disk.")
                    self.pg.execute_query("""
                        UPDATE project_documents
                        SET status = 'conflict', updated_at = NOW()
                        WHERE id = %s;
                    """, (doc_record["id"],))
                    return False, "conflict"

        # 3. Write document to disk atomically
        self.write_atomic(abs_path, content)

        # 4. Upsert PostgreSQL record
        new_version = (doc_record["version"] + 1) if (doc_record and doc_record["content_hash"] != new_hash) else (doc_record["version"] if doc_record else 1)
        upsert_sql = """
            INSERT INTO project_documents (
                id, project_id, document_type, relative_path, version, content_hash, status, last_synced_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'synced', NOW(), NOW(), NOW())
            ON CONFLICT (project_id, relative_path) DO UPDATE SET
                version = EXCLUDED.version,
                content_hash = EXCLUDED.content_hash,
                status = 'synced',
                last_synced_at = NOW(),
                updated_at = NOW();
        """
        self.pg.execute_query(upsert_sql, (
            str(uuid.uuid4()), project_id, document_type, relative_path, new_version, new_hash
        ))

        return True, "synced"

    def append_changelog(
        self,
        project_id: str,
        category: str,
        description: str,
        author: str = "system"
    ) -> None:
        """Appends a structured entry to changelog.md."""
        pdir = self.get_project_dir(project_id)
        changelog_path = os.path.join(pdir, "changelog.md")
        content = self.read_file(changelog_path) or f"# {project_id} Changelog\n\n"

        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        entry = f"\n### [{today}] - {category.title()}\n- {description} (by {author})\n"
        updated_content = content + entry
        self.sync_document(project_id, "changelog.md", "changelog", updated_content, force=True)

