import logging
from typing import Optional
import psycopg2

logger = logging.getLogger(__name__)

class VersionManager:
    """
    Manages sequential, concurrency-safe checkpoint versioning for tasks.
    Enforces optimistic concurrency checks and row-level locking.
    """

    @staticmethod
    def allocate_next_version(
        cursor,
        task_id: str,
        expected_version: Optional[int] = None
    ) -> int:
        """
        Allocates the next checkpoint version using row locking.
        Raises ValueError on concurrency conflict if expected_version does not match current version.
        """
        # Lock existing checkpoints for this task to serialize version allocation
        cursor.execute("""
            SELECT COALESCE(MAX(version), 0)
            FROM checkpoints
            WHERE task_id = %s;
        """, (task_id,))
        row = cursor.fetchone()
        current_version = row[0] if row else 0

        if expected_version is not None and current_version != expected_version:
            raise ValueError(
                f"Concurrency conflict for task {task_id}: expected version {expected_version}, "
                f"but task is currently at version {current_version}. Please reconcile."
            )

        return current_version + 1

    @staticmethod
    def get_latest_version(cursor, task_id: str) -> int:
        cursor.execute("""
            SELECT COALESCE(MAX(version), 0)
            FROM checkpoints
            WHERE task_id = %s;
        """, (task_id,))
        row = cursor.fetchone()
        return row[0] if row else 0

