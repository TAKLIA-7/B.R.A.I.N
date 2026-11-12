import pytest
from core.models.memory import ExtractedMemoryCandidate, MemoryType
from core.models.ingest import SourceMetadata, SourceType
from core.router.router import DeterministicRouter, StorageDestination, RoutingDecision

def test_temporary_context_routes_to_redis():
    router = DeterministicRouter()
    source = SourceMetadata(type=SourceType.TOOL, actor="debug_runner", trust_level=0.5)
    candidate = ExtractedMemoryCandidate(
        type=MemoryType.EXPERIENCE,
        text="Temporary debug stdout line 42",
        importance=0.2,
        requires_semantic_search=False
    )
    decision = router.route(candidate, source, is_temporary=True)
    assert StorageDestination.REDIS in decision.destinations
    assert decision.ttl_seconds is not None
    assert decision.ttl_seconds > 0

def test_durable_decision_routes_to_postgres_pgvector_and_neo4j():
    router = DeterministicRouter()
    source = SourceMetadata(type=SourceType.AGENT, actor="antigravity", trust_level=0.85)
    candidate = ExtractedMemoryCandidate(
        type=MemoryType.DECISION,
        subject="Project",
        predicate="USES",
        object="FastAPI",
        text="Decided to use FastAPI for REST interface",
        importance=0.9,
        requires_semantic_search=True,
        has_meaningful_relationships=True
    )
    decision = router.route(candidate, source, is_temporary=False)
    assert StorageDestination.POSTGRES in decision.destinations
    assert StorageDestination.PGVECTOR in decision.destinations
    assert StorageDestination.NEO4J in decision.destinations

def test_durable_fact_without_graph_relationships():
    router = DeterministicRouter()
    source = SourceMetadata(type=SourceType.USER, actor="alice", trust_level=0.95)
    candidate = ExtractedMemoryCandidate(
        type=MemoryType.FACT,
        text="The database port is 5432",
        importance=0.6,
        requires_semantic_search=True,
        has_meaningful_relationships=False
    )
    decision = router.route(candidate, source, is_temporary=False)
    assert StorageDestination.POSTGRES in decision.destinations
    assert StorageDestination.PGVECTOR in decision.destinations
    assert StorageDestination.NEO4J not in decision.destinations

