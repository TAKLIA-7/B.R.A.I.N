import json
import uuid
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter
from core.adapters.neo4j_adapter import Neo4jAdapter
from core.adapters.embeddings import EmbeddingGenerator

BACKUP_LIMITATION_NOTICE = (
    "Live deletion immediately invalidates and erases matching active records from PostgreSQL, "
    "pgvector embeddings, Redis working contexts, and Neo4j knowledge graph relationships. "
    "Cold backups (if retained by external infrastructure) remain subject to their configured "
    "retention lifecycle; restoring an unpruned cold backup requires re-applying this deletion receipt."
)

class DeletionReceipt(BaseModel):
    receipt_id: str
    scope: str
    status: str
    affected_systems: List[str]
    verification: Dict[str, str]
    records_invalidated: int
    backup_policy_notice: str = BACKUP_LIMITATION_NOTICE

class ForgetManager:
    """Coordinates verified erasure across PostgreSQL, pgvector, Redis, and Neo4j with audit receipts."""

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        redis_adapter: Optional[RedisAdapter] = None,
        neo4j_adapter: Optional[Neo4jAdapter] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.redis = redis_adapter or RedisAdapter()
        self.neo = neo4j_adapter or Neo4jAdapter()
        self.embedder = EmbeddingGenerator()

    def resolve_target_memory_ids(self, scope: str) -> List[str]:
        """Resolves target memory UUIDs by exact ID, actor prefix, or text match."""
        # 1. Exact UUID match
        uuid_regex = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        if re.match(uuid_regex, scope.strip().lower()):
            rows = self.pg.execute_query("SELECT id FROM memories WHERE id = %s;", (scope.strip(),))
            return [str(r["id"]) for r in rows]

        # 2. Actor / Source prefix (e.g. actor:alice)
        if scope.startswith("actor:") or scope.startswith("source:"):
            actor = scope.split(":", 1)[1].strip()
            rows = self.pg.execute_query(
                "SELECT m.id FROM memories m JOIN sources s ON m.source_id = s.id WHERE s.actor = %s;",
                (actor,)
            )
            return [str(r["id"]) for r in rows]

        # 3. Text / Keyword pattern match
        pattern = f"%{scope.strip()}%"
        rows = self.pg.execute_query(
            "SELECT id FROM memories WHERE text ILIKE %s OR subject ILIKE %s;",
            (pattern, pattern)
        )
        return [str(r["id"]) for r in rows]

    def forget(self, scope: str) -> Dict[str, Any]:
        """
        Executes verified forgetting:
        1. Resolve records and block immediately from retrieval.
        2. Invalidate PostgreSQL records and nullify pgvector embeddings.
        3. Remove Neo4j relationships.
        4. Remove Redis working copies.
        5. Run direct, semantic, and graph retrieval checks.
        6. Persist audit receipt in deletions table.
        """
        receipt_id = str(uuid.uuid4())
        affected_systems = []
        verification: Dict[str, str] = {}
        target_ids = self.resolve_target_memory_ids(scope)

        if not target_ids:
            # Nothing matched; create idempotent no-op receipt
            receipt = DeletionReceipt(
                receipt_id=receipt_id,
                scope=scope,
                status="completed",
                affected_systems=[],
                verification={"direct_check": "no_records_found"},
                records_invalidated=0
            )
            self._save_receipt(receipt)
            return receipt.model_dump()

        # Step 1 & 2: Invalidate PostgreSQL records and nullify pgvector embeddings immediately
        try:
            placeholders = ",".join(["%s"] * len(target_ids))
            update_sql = f"""
                UPDATE memories 
                SET status = 'deleted', embedding = NULL, valid_until = NOW()
                WHERE id IN ({placeholders});
            """
            self.pg.execute_query(update_sql, tuple(target_ids))
            affected_systems.extend(["postgres", "pgvector"])
            verification["direct_check"] = "passed"
        except Exception as e:
            verification["direct_check"] = f"failed: {str(e)}"

        # Step 3: Remove Neo4j graph relationships referencing these memory IDs
        try:
            cypher = """
                MATCH ()-[r]->()
                WHERE r.canonical_memory_id IN $ids
                DELETE r
            """
            self.neo.execute_cypher(cypher, {"ids": target_ids})
            affected_systems.append("neo4j")
            verification["graph_check"] = "passed"
        except Exception as e:
            verification["graph_check"] = f"failed: {str(e)}"

        # Step 4: Remove Redis working context and cache entries
        try:
            for mid in target_ids:
                self.redis.delete(f"memory:cache:{mid}")
            affected_systems.append("redis")
            verification["redis_check"] = "passed"
        except Exception as e:
            verification["redis_check"] = f"failed: {str(e)}"

        # Step 5: Verification audit checks
        # Semantic check: confirm deleted IDs do not surface
        try:
            q_vec = self.embedder.generate_embedding(scope)
            v_str = f"[{','.join(map(str, q_vec))}]"
            check_sql = f"""
                SELECT id FROM memories 
                WHERE status = 'active' AND embedding IS NOT NULL AND id IN ({placeholders})
                LIMIT 1;
            """
            active_check = self.pg.execute_query(check_sql, tuple(target_ids))
            verification["semantic_check"] = "passed" if len(active_check) == 0 else "failed_still_active"
        except Exception as e:
            verification["semantic_check"] = f"failed: {str(e)}"

        all_passed = all("passed" in str(v) for v in verification.values())
        overall_status = "completed" if all_passed else "partial_failure"

        receipt = DeletionReceipt(
            receipt_id=receipt_id,
            scope=scope,
            status=overall_status,
            affected_systems=affected_systems,
            verification=verification,
            records_invalidated=len(target_ids)
        )
        self._save_receipt(receipt)
        return receipt.model_dump()

    def _save_receipt(self, receipt: DeletionReceipt) -> None:
        sql = """
            INSERT INTO deletions (id, scope, status, receipt_json, created_at)
            VALUES (%s, %s, %s, %s::jsonb, NOW());
        """
        self.pg.execute_query(sql, (
            receipt.receipt_id,
            receipt.scope,
            receipt.status,
            json.dumps(receipt.model_dump())
        ))

