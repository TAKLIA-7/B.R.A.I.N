import pytest
import uuid
import time
from core.models.memory import ExtractedMemoryCandidate, MemoryType, EpistemicState
from core.models.ingest import SourceMetadata, SourceType
from core.router.router import DeterministicRouter, StorageDestination
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter
from core.adapters.neo4j_adapter import Neo4jAdapter
from core.adapters.embeddings import EmbeddingGenerator
from core.graph.sync import GraphSynchronizer
from core.store.outbox import OutboxProcessor

def test_redis_temporary_routing():
    router = DeterministicRouter()
    redis_adapter = RedisAdapter()
    
    session_id = f"session_test_{uuid.uuid4().hex[:8]}"
    content = "temporary working context data"
    
    # Store to redis via router
    key = router.store_temporary_context(session_id, content, ttl_seconds=30)
    assert redis_adapter.get(key) == content
    assert 0 < redis_adapter.get_ttl(key) <= 30
    
    redis_adapter.delete(key)

def test_postgres_pgvector_routing_and_search():
    pg = PostgresAdapter()
    embedder = EmbeddingGenerator()
    router = DeterministicRouter()

    # 1. Insert a source
    source_id = str(uuid.uuid4())
    pg.execute_query(
        "INSERT INTO sources (id, type, actor, trust_level) VALUES (%s, %s, %s, %s);",
        (source_id, "agent", "router_test_agent", 0.8)
    )

    # 2. Insert memory and generate embedding
    memory_id = str(uuid.uuid4())
    text_content = "PostgreSQL provides pgvector extension for high-performance vector similarity search."
    vector = embedder.generate_embedding(text_content)
    assert len(vector) == embedder.dimension

    vector_str = f"[{','.join(map(str, vector))}]"
    pg.execute_query(
        """
        INSERT INTO memories (id, type, text, status, epistemic_state, source_id, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s::vector);
        """,
        (memory_id, "fact", text_content, "active", "asserted", source_id, vector_str)
    )

    # 3. Perform semantic similarity search using pgvector cosine distance (<=>)
    query_vector = embedder.generate_embedding("vector similarity search in postgres")
    query_vector_str = f"[{','.join(map(str, query_vector))}]"
    
    results = pg.execute_query(
        """
        SELECT id, text, (embedding <=> %s::vector) AS distance
        FROM memories
        WHERE id = %s
        ORDER BY distance ASC;
        """,
        (query_vector_str, memory_id)
    )
    assert len(results) == 1
    assert results[0]["id"] == memory_id
    assert results[0]["distance"] is not None

def test_neo4j_graph_synchronization_with_pg_reference():
    pg = PostgresAdapter()
    graph_sync = GraphSynchronizer()
    neo = Neo4jAdapter()

    memory_id = str(uuid.uuid4())
    subject = "KnowledgeBrain"
    predicate = "USES"
    object_entity = "PostgreSQL"

    # Synchronize to Neo4j
    graph_sync.sync_memory_relationship(
        memory_id=memory_id,
        subject=subject,
        predicate=predicate,
        object_entity=object_entity,
        epistemic_state="asserted"
    )

    # Query Neo4j directly and verify relationship and PG memory ID reference
    query = """
        MATCH (s {name: $subject})-[r:USES]->(o {name: $object})
        WHERE r.canonical_memory_id = $memory_id
        RETURN s.name AS s_name, type(r) AS rel_type, o.name AS o_name, r.epistemic_state AS state
    """
    records = neo.execute_cypher(query, {
        "subject": subject,
        "object": object_entity,
        "memory_id": memory_id
    })
    assert len(records) >= 1
    assert records[0]["s_name"] == subject
    assert records[0]["rel_type"] == predicate
    assert records[0]["o_name"] == object_entity
    assert records[0]["state"] == "asserted"

def test_outbox_retry_idempotence():
    pg = PostgresAdapter()
    outbox = OutboxProcessor()
    
    event_id = str(uuid.uuid4())
    memory_id = str(uuid.uuid4())
    payload = {
        "memory_id": memory_id,
        "subject": "SystemArchitecture",
        "predicate": "DEFINES",
        "object": "DeterministicRouter",
        "epistemic_state": "confirmed"
    }

    # Insert outbox event
    outbox.enqueue_event("sync_graph", payload, event_id=event_id)

    # Process outbox event first time
    processed_first = outbox.process_pending_events()
    assert processed_first >= 1

    # Check status is completed
    rows = pg.execute_query("SELECT status, retry_count FROM outbox_events WHERE id = %s;", (event_id,))
    assert rows[0]["status"] == "completed"

    # Re-run outbox processing: must be idempotent and not duplicate
    processed_second = outbox.process_pending_events()
    assert processed_second == 0  # No pending events left

