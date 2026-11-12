import json
import uuid
from typing import Dict, Any, Optional
from core.models.checkpoint import HandoverState
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter

class CheckpointManager:
    """Manages immutable versioned checkpoints in PostgreSQL with active cache in Redis."""

    def __init__(self, postgres_adapter: Optional[PostgresAdapter] = None, redis_adapter: Optional[RedisAdapter] = None):
        self.pg = postgres_adapter or PostgresAdapter()
        self.redis = redis_adapter or RedisAdapter()

    def create_task(self, task_id: str, goal: str, created_by: str) -> Dict[str, Any]:
        sql = """
            INSERT INTO tasks (id, goal, created_by, created_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET goal = EXCLUDED.goal
            RETURNING id, goal, created_by, created_at;
        """
        rows = self.pg.execute_query(sql, (task_id, goal, created_by))
        return rows[0]

    def save_checkpoint(self, task_id: str, state: HandoverState) -> Dict[str, Any]:
        """
        Persists a new version of the checkpoint in PostgreSQL.
        Maintains unique constraint (task_id, version).
        """
        # Ensure task exists
        self.create_task(task_id, state.goal, state.written_by)

        # Determine next version number
        ver_sql = "SELECT COALESCE(MAX(version), 0) + 1 AS next_ver FROM checkpoints WHERE task_id = %s;"
        ver_row = self.pg.execute_query(ver_sql, (task_id,))
        next_version = ver_row[0]["next_ver"]

        checkpoint_id = str(uuid.uuid4())
        state_dict = state.model_dump()

        insert_sql = """
            INSERT INTO checkpoints (id, task_id, version, state_json, written_by, created_at)
            VALUES (%s, %s, %s, %s::jsonb, %s, NOW())
            RETURNING id, task_id, version, state_json, written_by, created_at;
        """
        rows = self.pg.execute_query(
            insert_sql,
            (checkpoint_id, task_id, next_version, json.dumps(state_dict), state.written_by)
        )
        saved = rows[0]

        # Store working copy in Redis for fast access (TTL: 2 hours)
        self.redis.set_with_ttl(f"task:working:{task_id}", json.dumps(state_dict), ttl_seconds=7200)

        return saved

    def get_latest_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Always queries canonical PostgreSQL source of truth for the latest version.
        Redis is never the sole repository for durable checkpoints.
        """
        sql = """
            SELECT id, task_id, version, state_json, written_by, created_at
            FROM checkpoints
            WHERE task_id = %s
            ORDER BY version DESC
            LIMIT 1;
        """
        rows = self.pg.execute_query(sql, (task_id,))
        return rows[0] if rows else None

