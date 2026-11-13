import json
import logging
import subprocess
import uuid
from typing import Dict, Any, List, Optional
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter
from core.handoff.schemas import CheckpointState
from core.handoff.versioning import VersionManager

logger = logging.getLogger(__name__)

class CheckpointService:
    """
    Transaction-safe service for saving and retrieving versioned task checkpoints.
    PostgreSQL is the authoritative store; Redis holds working state.
    """

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        redis_adapter: Optional[RedisAdapter] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.redis = redis_adapter or RedisAdapter()

    def _detect_git_metadata(self) -> Dict[str, Optional[str]]:
        commit = None
        branch = None
        try:
            c_proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if c_proc.returncode == 0:
                commit = c_proc.stdout.strip()

            b_proc = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if b_proc.returncode == 0:
                branch = b_proc.stdout.strip()
        except Exception:
            pass
        return {"commit": commit, "branch": branch}

    def create_task(
        self,
        task_id: str,
        goal: str,
        created_by: str,
        status: str = "in_progress"
    ) -> Dict[str, Any]:
        """Creates or initializes a task record in PostgreSQL."""
        sql = """
            INSERT INTO tasks (id, goal, created_by, current_owner, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (id) DO UPDATE SET
                goal = EXCLUDED.goal,
                current_owner = EXCLUDED.current_owner,
                status = EXCLUDED.status,
                updated_at = NOW()
            RETURNING id, goal, created_by, current_owner, status, created_at, updated_at;
        """
        rows = self.pg.execute_query(sql, (task_id, goal, created_by, created_by, status))
        return rows[0] if rows else {}

    def update_task_owner(self, task_id: str, new_owner: str) -> None:
        """Updates task current owner and timestamp."""
        sql = """
            UPDATE tasks
            SET current_owner = %s,
                updated_at = NOW()
            WHERE id = %s;
        """
        self.pg.execute_query(sql, (new_owner, task_id))

    def save_checkpoint(
        self,
        task_id_or_state: Any = None,
        state: Optional[Any] = None,
        expected_version: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Saves a structured checkpoint transactionally.
        Ensures strict version progression, updates task metadata, and caches in Redis.
        """
        actual_state = state
        if actual_state is None:
            if isinstance(task_id_or_state, (CheckpointState, dict)):
                actual_state = task_id_or_state
            elif "state" in kwargs:
                actual_state = kwargs["state"]

        if isinstance(task_id_or_state, str) and actual_state is not None:
            if isinstance(actual_state, dict) and "task_id" not in actual_state:
                actual_state["task_id"] = task_id_or_state

        if isinstance(actual_state, dict):
            actual_state = CheckpointState.model_validate(actual_state)

        if not isinstance(actual_state, CheckpointState):
            raise ValueError(f"Invalid state provided for checkpoint: {type(actual_state)}")

        # Ensure task exists in PostgreSQL
        self.create_task(
            task_id=actual_state.task_id,
            goal=actual_state.goal,
            created_by=actual_state.written_by
        )

        # Detect git info if not explicitly supplied
        git_info = self._detect_git_metadata()
        git_commit = actual_state.git_commit or git_info.get("commit")
        git_branch = actual_state.git_branch or git_info.get("branch")

        checkpoint_id = str(uuid.uuid4())
        state_dict = actual_state.model_dump()
        state_json = json.dumps(state_dict)

        with self.pg.get_connection() as conn:
            with conn.cursor() as cur:
                # 1. Allocate next version with row lock & concurrency check
                next_version = VersionManager.allocate_next_version(
                    cursor=cur,
                    task_id=actual_state.task_id,
                    expected_version=expected_version
                )

                # 2. Insert immutable checkpoint record
                insert_sql = """
                    INSERT INTO checkpoints (
                        id, task_id, version, state_json, written_by,
                        git_commit, git_branch, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW());
                """
                cur.execute(insert_sql, (
                    checkpoint_id,
                    actual_state.task_id,
                    next_version,
                    state_json,
                    actual_state.written_by,
                    git_commit,
                    git_branch
                ))

                # 3. Update task current_owner and timestamp
                update_task_sql = """
                    UPDATE tasks
                    SET current_owner = %s,
                        updated_at = NOW()
                    WHERE id = %s;
                """
                cur.execute(update_task_sql, (actual_state.written_by, actual_state.task_id))

        # 4. Cache working state in Redis with TTL
        try:
            self.redis.set_with_ttl(
                f"task:working:{actual_state.task_id}",
                state_json,
                ttl_seconds=86400  # 24 hour working cache
            )
        except Exception as e:
            logger.warning(f"Failed to cache working state in Redis: {e}")

        # 5. Synchronize project checkpoint.md if project_id or sync_markdown specified
        project_id = kwargs.get("project_id")
        sync_markdown = kwargs.get("sync_markdown", False)
        if project_id or sync_markdown:
            try:
                from core.project_knowledge.synchronizer import ProjectDocumentSynchronizer
                from core.agent_monitor.checkpoint_generator import CheckpointMarkdownGenerator
                from core.agent_monitor.git_inspector import GitInspector
                p_id = project_id
                if not p_id:
                    p_rows = self.pg.execute_query("SELECT project_id FROM tasks WHERE id = %s;", (actual_state.task_id,))
                    if p_rows and p_rows[0].get("project_id"):
                        p_id = p_rows[0]["project_id"]
                if p_id:
                    sync = ProjectDocumentSynchronizer(postgres_adapter=self.pg)
                    git_state = GitInspector().inspect()
                    md = CheckpointMarkdownGenerator.generate_checkpoint_md(
                        state=actual_state,
                        project_id=p_id,
                        checkpoint_version=next_version,
                        trigger_reason=kwargs.get("trigger_reason", "manual"),
                        session_id=kwargs.get("session_id"),
                        git_state=git_state
                    )
                    sync.sync_document(p_id, "checkpoint.md", "checkpoint", md, force=False)
                    sync.sync_document(p_id, f"checkpoints/checkpoint_v{next_version}.md", "checkpoint_history", md, force=True)
            except Exception as e:
                logger.warning(f"Could not synchronize checkpoint.md: {e}")

        logger.info(f"Saved checkpoint v{next_version} for task {actual_state.task_id} by {actual_state.written_by}")

        return {
            "success": True,
            "task_id": actual_state.task_id,
            "checkpoint_version": next_version,
            "version": next_version,
            "checkpoint_id": checkpoint_id,
            "written_by": actual_state.written_by
        }

    def get_latest_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the latest canonical checkpoint from PostgreSQL."""
        sql = """
            SELECT id, task_id, version, state_json, written_by, git_commit, git_branch, created_at
            FROM checkpoints
            WHERE task_id = %s
            ORDER BY version DESC
            LIMIT 1;
        """
        rows = self.pg.execute_query(sql, (task_id,))
        if not rows:
            return None

        row = rows[0]
        state = row["state_json"]
        if isinstance(state, str):
            state = json.loads(state)

        return {
            "id": str(row["id"]),
            "task_id": row["task_id"],
            "version": row["version"],
            "state_json": state,
            "written_by": row["written_by"],
            "git_commit": row.get("git_commit"),
            "git_branch": row.get("git_branch"),
            "created_at": str(row["created_at"])
        }

    def get_checkpoint_history(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieves all historical checkpoints for a task ordered by version ascending."""
        sql = """
            SELECT id, task_id, version, written_by, git_commit, git_branch, created_at
            FROM checkpoints
            WHERE task_id = %s
            ORDER BY version ASC;
        """
        rows = self.pg.execute_query(sql, (task_id,))
        results = []
        for r in rows:
            results.append({
                "id": str(r["id"]),
                "task_id": r["task_id"],
                "version": r["version"],
                "written_by": r["written_by"],
                "git_commit": r.get("git_commit"),
                "git_branch": r.get("git_branch"),
                "created_at": str(r["created_at"])
            })
        return results

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Returns task metadata, status, current owner, and latest checkpoint version."""
        sql = """
            SELECT t.id, t.goal, t.status, t.created_by, t.current_owner, t.created_at, t.updated_at,
                   COALESCE(MAX(c.version), 0) AS latest_version
            FROM tasks t
            LEFT JOIN checkpoints c ON t.id = c.task_id
            WHERE t.id = %s
            GROUP BY t.id, t.goal, t.status, t.created_by, t.current_owner, t.created_at, t.updated_at;
        """
        rows = self.pg.execute_query(sql, (task_id,))
        if not rows:
            return {"status": "not_found", "task_id": task_id}

        r = rows[0]
        return {
            "task_id": r["id"],
            "goal": r["goal"],
            "status": r["status"],
            "created_by": r["created_by"],
            "current_owner": r["current_owner"],
            "latest_version": r["latest_version"],
            "created_at": str(r["created_at"]),
            "updated_at": str(r["updated_at"])
        }

# Alias for backwards compatibility
CheckpointManager = CheckpointService
