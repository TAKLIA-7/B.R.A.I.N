import pytest
import uuid
from core.models.ingest import IngestRequest, SourceMetadata, SourceType
from core.store.ingest import IngestionCoordinator
from core.forget.forget_manager import ForgetManager
from core.retrieve.retriever import HybridRetriever
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter
from core.adapters.neo4j_adapter import Neo4jAdapter

def test_verified_forgetting_multi_store_erasure():
    coordinator = IngestionCoordinator()
    forget_mgr = ForgetManager()
    retriever = HybridRetriever()
    pg = PostgresAdapter()
    redis = RedisAdapter()
    neo = Neo4jAdapter()

    # 1. Ingest memory to be forgotten
    secret_text = f"CONFIDENTIAL CREDENTIAL {uuid.uuid4().hex}: Payment gateway token is tok_live_abc123"
    req = IngestRequest(
        source=SourceMetadata(type=SourceType.USER, actor="admin_user", trust_level=0.9),
        content=secret_text
    )
    ingest_res = coordinator.process_ingestion(req)
    assert len(ingest_res.memories) >= 1
    memory_id = ingest_res.memories[0]["id"]

    # Explicitly set relationship and redis key for test completeness
    neo.execute_cypher(
        "MERGE (s:Entity {name: 'PaymentGateway'}) MERGE (o:Entity {name: 'LiveToken'}) MERGE (s)-[r:USES {canonical_memory_id: $mid}]->(o)",
        {"mid": memory_id}
    )
    redis.set_with_ttl(f"memory:cache:{memory_id}", secret_text, ttl_seconds=600)

    # 2. Execute verified forgetting
    receipt = forget_mgr.forget(scope=memory_id)
    assert receipt["status"] == "completed"
    assert receipt["records_invalidated"] >= 1
    assert "receipt_id" in receipt

    # 3. Direct PostgreSQL check: status is 'deleted' and embedding is NULL
    rows = pg.execute_query("SELECT status, embedding FROM memories WHERE id = %s;", (memory_id,))
    assert len(rows) == 1
    assert rows[0]["status"] == "deleted"
    assert rows[0]["embedding"] is None

    # 4. Semantic search check: forgotten content must no longer surface
    search_res = retriever.search(query="Payment gateway live token tok_live_abc123", token_budget=300)
    assert not any(m["id"] == memory_id for m in search_res.get("memories", []))

    # 5. Neo4j check: graph relationships must no longer exist
    neo_rows = neo.execute_cypher("MATCH ()-[r {canonical_memory_id: $mid}]->() RETURN r", {"mid": memory_id})
    assert len(neo_rows) == 0

    # 6. Redis check: cache key must be deleted
    assert redis.get(f"memory:cache:{memory_id}") is None

    # 7. PostgreSQL deletions audit receipt check
    del_rows = pg.execute_query("SELECT id, scope, status, receipt_json FROM deletions WHERE id = %s;", (receipt["receipt_id"],))
    assert len(del_rows) == 1
    assert del_rows[0]["status"] == "completed"
    assert "backup" in del_rows[0]["receipt_json"]["backup_policy_notice"].lower()

def test_forgetting_by_text_scope():
    coordinator = IngestionCoordinator()
    forget_mgr = ForgetManager()
    pg = PostgresAdapter()

    keyword = f"ephemeral_token_{uuid.uuid4().hex[:6]}"
    req = IngestRequest(
        source=SourceMetadata(type=SourceType.USER, actor="alice", trust_level=0.9),
        content=f"Secret session string containing {keyword} for authentication."
    )
    coordinator.process_ingestion(req)

    # Forget by keyword scope
    receipt = forget_mgr.forget(scope=keyword)
    assert receipt["status"] == "completed"
    assert receipt["records_invalidated"] >= 1

    # Verify no active memories contain keyword
    rows = pg.execute_query(
        "SELECT id FROM memories WHERE text ILIKE %s AND status = 'active';",
        (f"%{keyword}%",)
    )
    assert len(rows) == 0

