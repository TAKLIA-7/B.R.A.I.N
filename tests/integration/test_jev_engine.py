import uuid
import pytest
from core.adapters.postgres import PostgresAdapter
from core.jev.engine import JEVDecisionEngine
from core.jev.contracts import MemoryDecision, RetrievalDecision, HandoverDecision
from core.models.ingest import IngestRequest, SourceMetadata, SourceType

@pytest.fixture
def pg():
    return PostgresAdapter()

@pytest.fixture
def jev_engine(pg):
    return JEVDecisionEngine(postgres_adapter=pg)

def test_jev_decide_ingestion_and_audit_logging(jev_engine, pg):
    text = "We decided to enforce a 3600-second TTL on all Redis temporary session keys."
    req = IngestRequest(
        source=SourceMetadata(type=SourceType.AGENT, actor="Agent-A", trust_level=0.9),
        content=text
    )

    items, audit_record = jev_engine.decide_ingestion(req)
    assert len(items) >= 1
    item = items[0]
    assert isinstance(item.decision, MemoryDecision)
    assert item.decision.memory_type == "decision"
    assert "postgres" in item.decision.storage_targets

    # Verify audit record in PostgreSQL
    assert audit_record["operation_type"] == "ingest"
    assert audit_record["validation_status"] == "passed"

    # Query PostgreSQL jev_decisions table directly to verify persistence
    with pg.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT operation_type, validation_status, fallback_used, model
                FROM jev_decisions
                WHERE decision_id = %s;
            """, (audit_record["decision_id"],))
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "ingest"
            assert row[1] == "passed"

def test_jev_decide_retrieval(jev_engine):
    query = "Find architecture decisions about PostgreSQL and pgvector storage"
    decision, audit_record = jev_engine.decide_retrieval(query=query, token_budget=600)

    assert isinstance(decision, RetrievalDecision)
    assert decision.token_budget == 600
    assert decision.include_semantic_search is True
    assert audit_record["operation_type"] == "retrieve"

def test_jev_decide_handover(jev_engine, pg):
    task_id = f"task-jev-handover-{uuid.uuid4().hex[:6]}"
    # Seed task and checkpoint in PostgreSQL
    with pg.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO tasks (id, goal, created_by)
                VALUES (%s, 'Demonstrate JEV Handover', 'Agent-A')
                ON CONFLICT (id) DO NOTHING;
            """, (task_id,))
            cur.execute("""
                INSERT INTO checkpoints (task_id, version, state_json, written_by)
                VALUES (%s, 1, '{"task_id": "%s", "goal": "Build REST API", "steps": [{"description": "Init DB", "status": "completed"}], "decisions": ["Postgres selected"], "rejected": [], "open_questions": [], "written_by": "Agent-A"}'::jsonb, 'Agent-A')
                ON CONFLICT (task_id, version) DO NOTHING;
            """ % (f"'{task_id}'", task_id))

    decision, audit_record = jev_engine.decide_handover(task_id=task_id, token_budget=1000)
    assert isinstance(decision, HandoverDecision)
    assert decision.task_id == task_id
    assert decision.token_budget == 1000
    assert audit_record["operation_type"] == "handover"

def test_jev_decide_conflict(jev_engine):
    existing_memory = {
        "memory_id": "mem-001",
        "text": "Redis TTL is set to 1800 seconds",
        "trust_score": 0.6,
        "epistemic_state": "asserted"
    }
    new_claim = "Redis TTL is strictly 3600 seconds verified by production config"
    
    decision, audit = jev_engine.decide_conflict(
        existing_memory=existing_memory,
        new_claim=new_claim,
        new_trust_level=0.95
    )
    assert decision.conflict_detected is True
    assert decision.conflicting_memory_id == "mem-001"
    assert decision.resolution in ("supersede", "dispute")
    assert audit["operation_type"] == "conflict"

def test_jev_graceful_fallback_when_disabled(pg):
    engine = JEVDecisionEngine(postgres_adapter=pg, enabled=False)
    query = "Search storage settings"
    decision, audit = engine.decide_retrieval(query=query, token_budget=400)
    assert isinstance(decision, RetrievalDecision)
    assert audit["fallback_used"] is True

