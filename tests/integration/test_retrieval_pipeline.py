import pytest
import uuid
from core.retrieve.retriever import HybridRetriever
from core.adapters.postgres import PostgresAdapter
from core.adapters.neo4j_adapter import Neo4jAdapter
from core.models.ingest import IngestRequest, SourceMetadata, SourceType
from core.store.ingest import IngestionCoordinator

def test_semantic_retrieval_with_provenance_and_ranking():
    coordinator = IngestionCoordinator()
    retriever = HybridRetriever()

    # Ingest test memory
    req = IngestRequest(
        source=SourceMetadata(type=SourceType.AGENT, actor="retrieval_test_agent", trust_level=0.85),
        content="FastAPI router handles incoming HTTP REST API requests asynchronously."
    )
    coordinator.process_ingestion(req)

    # Search for semantic match
    result = retriever.search(query="asynchronous HTTP REST routing", token_budget=200)
    assert result["abstain"] is False
    assert len(result["memories"]) >= 1

    top_memory = result["memories"][0]
    assert "FastAPI" in top_memory["text"] or "HTTP" in top_memory["text"]
    assert top_memory["epistemic_state"] in ("asserted", "confirmed", "disputed")
    assert "actor" in top_memory["provenance"]
    assert top_memory["provenance"]["actor"] == "retrieval_test_agent"
    assert "trust_level" in top_memory["provenance"]

def test_graph_relationship_retrieval():
    neo = Neo4jAdapter()
    retriever = HybridRetriever()

    # Create relationship in Neo4j
    subj = "BrainArchitecture"
    obj = "PgVector"
    neo.execute_cypher(
        """
        MERGE (s:Entity {name: $s})
        MERGE (o:Entity {name: $o})
        MERGE (s)-[r:USES {canonical_memory_id: 'mem-graph-test-01', epistemic_state: 'asserted'}]->(o)
        """,
        {"s": subj, "o": obj}
    )

    result = retriever.search(query="What does BrainArchitecture use?", token_budget=300)
    assert result["abstain"] is False
    # Graph relationships should be populated
    assert "graph_relationships" in result
    assert any(
        r["subject"] == subj and r["object"] == obj
        for r in result["graph_relationships"]
    )

def test_matching_bug_history_included():
    pg = PostgresAdapter()
    retriever = HybridRetriever()

    bug_id = f"BUG-{uuid.uuid4().hex[:6].upper()}"
    pg.execute_query(
        """
        INSERT INTO bugs (bug_id, title, symptom, root_cause, status, severity, location, reported_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (bug_id) DO NOTHING;
        """,
        (
            bug_id,
            "Postgres connection pool exhaustion under load",
            "Timeout connecting to database",
            "Missing pool recycling",
            "investigating",
            "high",
            '{"repo": "BRAIN", "files": ["core/adapters/postgres.py"], "symbols": ["get_connection"]}',
            "qa-agent"
        )
    )

    # Search for postgres connection pool bug
    result = retriever.search(query="postgres connection timeout core/adapters/postgres.py", token_budget=500)
    assert "bug_history" in result
    assert any(b["bug_id"] == bug_id for b in result["bug_history"])

def test_abstention_on_unknown_query():
    retriever = HybridRetriever()
    result = retriever.search(query="completely unrelated query regarding ancient aztec astronomy", token_budget=100)
    assert result["abstain"] is True
    assert result["message"] == "no supporting memory"
    assert len(result["memories"]) == 0

