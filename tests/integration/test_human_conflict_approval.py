"""
tests/integration/test_human_conflict_approval.py
Comprehensive integration tests for Human-in-the-Loop Conflict Resolution:
- Mandatory approval pause on ambiguous / conflicting claims
- Canonical knowledge remains unchanged while pending
- Human authorization enforcement (agents cannot approve own conflicts)
- Approval execution (canonical supersede, outbox sync, Markdown update)
- Human rejection (active knowledge untouched, rejected claim never synced)
- Clarification and re-evaluation workflow
- Stale approval prevention via optimistic concurrency
- Ingestion pipeline integration
- REST API and MCP tool verification
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from core.adapters.postgres import PostgresAdapter
from core.conflict.manager import ConflictManager
from core.conflict.schemas import ConflictState, ConflictResolution, HumanApprovalAction
from core.conflict.rules import RULE_AMBIGUOUS_INSTRUCTION, RULE_CRITICAL_ARCHITECTURE_IMPACT
from core.models.ingest import IngestRequest, SourceMetadata, SourceType
from core.store.ingest import IngestionCoordinator
from core.project_knowledge.manager import ProjectKnowledgeManager
from core.project_knowledge.schemas import ProjectCreateRequest
from core.evolution.manager import RequirementManager
from core.evolution.schemas import RequirementCreateRequest
from api import app
from mcp_server import (
    memory_conflicts_list,
    memory_conflict_get,
    memory_conflict_approve,
    memory_conflict_reject,
    memory_conflict_clarify,
    memory_check_conflict
)


@pytest.fixture
def pg():
    return PostgresAdapter()


@pytest.fixture
def conflict_mgr(pg):
    return ConflictManager(postgres_adapter=pg)


@pytest.fixture
def sample_project(pg):
    pid = f"test-conf-proj-{uuid.uuid4().hex[:6]}"
    mgr = ProjectKnowledgeManager(postgres_adapter=pg)
    req = ProjectCreateRequest(id=pid, name=f"Conflict Test Project {pid}")
    p = mgr.register_project(req)
    yield p
    # Teardown
    import shutil
    from core.project_knowledge.synchronizer import ProjectDocumentSynchronizer
    sync = ProjectDocumentSynchronizer(postgres_adapter=pg)
    pdir = sync.get_project_dir(pid)
    if os.path.exists(pdir):
        shutil.rmtree(pdir, ignore_errors=True)
    try:
        pg.execute_query("DELETE FROM projects WHERE id = %s;", (pid,))
    except Exception:
        pass


import os


def test_conflict_detection_pauses_canonical_change(pg, conflict_mgr):
    """Verify that an ambiguous contradiction pauses update and does NOT change active canonical memory."""
    # 1. Setup existing canonical active memory
    mem_id = str(uuid.uuid4())
    pg.execute_query("""
        INSERT INTO memories (id, type, text, status, epistemic_state, created_at)
        VALUES (%s, 'decision', 'We use PostgreSQL for all relational storage.', 'active', 'confirmed', NOW());
    """, (mem_id,))

    # 2. Incoming ambiguous claim from an agent
    claim = "Maybe we should migrate relational storage to MongoDB."
    is_conf, item = conflict_mgr.check_and_register_conflict(
        incoming_claim=claim,
        source_actor="autonomous-agent-1",
        trust_level=0.7
    )

    assert is_conf is True
    assert item is not None
    assert item.status == ConflictState.PENDING_HUMAN_APPROVAL.value
    assert RULE_AMBIGUOUS_INSTRUCTION in item.applicable_rule_ids
    assert RULE_CRITICAL_ARCHITECTURE_IMPACT in item.applicable_rule_ids

    # 3. CRITICAL: Verify existing memory is STILL active and untouched
    rows = pg.execute_query("SELECT status, epistemic_state FROM memories WHERE id = %s;", (mem_id,))
    assert len(rows) == 1
    assert rows[0]["status"] == "active"
    assert rows[0]["epistemic_state"] == "confirmed"

    # Verify new claim has NOT been inserted into active memories
    new_rows = pg.execute_query("SELECT id FROM memories WHERE text = %s AND status = 'active';", (claim,))
    assert len(new_rows) == 0


def test_agent_cannot_approve_own_conflict(conflict_mgr):
    """Verify that AI agents are forbidden from approving their own conflicts."""
    is_conf, item = conflict_mgr.check_and_register_conflict(
        incoming_claim="Planning to change auth from JWT to session cookies.",
        source_actor="coding-agent-2"
    )
    assert is_conf is True

    # 1. Attempt approval with agent actor -> PermissionError
    with pytest.raises(PermissionError, match="AI agents must not approve their own ambiguous conflicts"):
        conflict_mgr.approve_conflict(
            conflict_id=item.conflict_id,
            approver="coding-agent-2",
            is_human=False
        )

    # 2. Attempt approval with is_human=False -> PermissionError
    with pytest.raises(PermissionError):
        conflict_mgr.approve_conflict(
            conflict_id=item.conflict_id,
            approver="Tanish",
            is_human=False
        )


def test_human_approval_workflow(pg, conflict_mgr, sample_project):
    """Verify authorized human approval supersedes old memory and updates status to resolved."""
    pid = sample_project.id
    mem_id = str(uuid.uuid4())
    pg.execute_query("""
        INSERT INTO memories (id, type, text, status, epistemic_state, created_at)
        VALUES (%s, 'decision', 'Database is PostgreSQL 16', 'active', 'confirmed', NOW());
    """, (mem_id,))

    claim = "Switch database engine to MongoDB 7"
    is_conf, item = conflict_mgr.check_and_register_conflict(
        incoming_claim=claim,
        source_actor="agent-refactor",
        project_id=pid
    )
    assert is_conf is True

    # Authorized human approves
    res = conflict_mgr.approve_conflict(
        conflict_id=item.conflict_id,
        approver="LeadArchitect_Tanish",
        rationale="Approved after architectural review",
        selected_resolution="supersede",
        is_human=True
    )
    assert res["success"] is True
    assert res["status"] == "resolved"
    assert res["resolution"] == "supersede"

    # Verify old memory is now superseded
    old_rows = pg.execute_query("SELECT status, valid_until FROM memories WHERE id = %s;", (mem_id,))
    assert old_rows[0]["status"] == "superseded"
    assert old_rows[0]["valid_until"] is not None

    # Verify new memory is active
    new_rows = pg.execute_query("SELECT status, epistemic_state, supersedes_id FROM memories WHERE id = %s;", (res["new_memory_id"],))
    assert len(new_rows) == 1
    assert new_rows[0]["status"] == "active"
    assert new_rows[0]["epistemic_state"] == "confirmed"
    assert str(new_rows[0]["supersedes_id"]) == mem_id


def test_human_rejection_preserves_active_knowledge(pg, conflict_mgr):
    """Verify human rejection preserves existing active knowledge and never synchronizes rejected claim."""
    mem_id = str(uuid.uuid4())
    pg.execute_query("""
        INSERT INTO memories (id, type, text, status, epistemic_state, created_at)
        VALUES (%s, 'decision', 'Authentication uses RS256 JWT tokens.', 'active', 'confirmed', NOW());
    """, (mem_id,))

    claim = "Tentatively disable signature checking on JWT tokens."
    is_conf, item = conflict_mgr.check_and_register_conflict(
        incoming_claim=claim,
        source_actor="agent-test"
    )
    assert is_conf is True

    # Human rejects the change
    res = conflict_mgr.reject_conflict(
        conflict_id=item.conflict_id,
        approver="SecurityLead_Tanish",
        rationale="Insecure proposed change rejected",
        is_human=True
    )
    assert res["success"] is True
    assert res["status"] == "rejected"
    assert res["canonical_knowledge_preserved"] is True

    # Existing active knowledge is completely untouched
    old_rows = pg.execute_query("SELECT status FROM memories WHERE id = %s;", (mem_id,))
    assert old_rows[0]["status"] == "active"

    # Rejected claim was never inserted into memories
    new_rows = pg.execute_query("SELECT id FROM memories WHERE text = %s;", (claim,))
    assert len(new_rows) == 0


def test_clarification_workflow(conflict_mgr):
    """Verify submitting clarification keeps conflict pending and updates evidence."""
    is_conf, item = conflict_mgr.check_and_register_conflict(
        incoming_claim="Maybe switch cache to Redis cluster.",
        source_actor="agent-cache"
    )
    assert is_conf is True

    # Submit clarification
    updated_item = conflict_mgr.submit_clarification(
        conflict_id=item.conflict_id,
        author="DevOps_Agent",
        clarification_notes="Benchmarking shows Redis cluster reduces latency by 40%",
        updated_claim="Migrate single Redis instance to Redis Cluster mode",
        additional_evidence={"benchmark_proof": "latency_report.pdf"}
    )

    assert updated_item.clarification_response == "Benchmarking shows Redis cluster reduces latency by 40%"
    assert updated_item.incoming_claim == "Migrate single Redis instance to Redis Cluster mode"
    assert "benchmark_proof" in updated_item.evidence_and_provenance
    # Conflict is still pending human review; silence is never approval
    assert updated_item.status in [ConflictState.PENDING_HUMAN_APPROVAL.value, ConflictState.EVALUATING.value]


def test_stale_approval_optimistic_concurrency(pg, conflict_mgr):
    """Verify that if target memory was already modified, approval is rejected as stale."""
    mem_id = str(uuid.uuid4())
    pg.execute_query("""
        INSERT INTO memories (id, type, text, status, epistemic_state, created_at)
        VALUES (%s, 'decision', 'Initial framework is FastAPI', 'active', 'confirmed', NOW());
    """, (mem_id,))

    is_conf, item = conflict_mgr.check_and_register_conflict(
        incoming_claim="Switch framework to Django",
        source_actor="agent-1"
    )
    assert is_conf is True

    # Concurrently supersede target memory before approval is executed
    pg.execute_query("UPDATE memories SET status = 'superseded' WHERE id = %s;", (mem_id,))

    # Human attempts to approve stale conflict -> ValueError
    with pytest.raises(ValueError, match="Stale approval conflict"):
        conflict_mgr.approve_conflict(
            conflict_id=item.conflict_id,
            approver="Architect",
            is_human=True
        )


def test_ingestion_coordinator_conflict_pause(pg):
    """Verify that IngestionCoordinator pauses ingestion when a high-impact contradiction is detected."""
    # Seed active memory
    mem_id = str(uuid.uuid4())
    pg.execute_query("""
        INSERT INTO memories (id, type, text, status, epistemic_state, created_at)
        VALUES (%s, 'decision', 'We use PostgreSQL for all relational storage.', 'active', 'confirmed', NOW());
    """, (mem_id,))

    coordinator = IngestionCoordinator(postgres_adapter=pg)
    req = IngestRequest(
        content="Maybe we should switch our relational storage from PostgreSQL to MySQL.",
        source=SourceMetadata(actor="agent-refactor", type=SourceType.AGENT, trust_level=0.7)
    )

    resp = coordinator.process_ingestion(req)
    # The conflicting item was paused for human approval
    assert len(resp.memories) >= 1
    assert any(m["status"] == "pending_human_approval" for m in resp.memories)


def test_rest_api_conflict_endpoints(pg):
    """Verify REST API /conflicts/pending, /conflicts/{id}, /conflicts/{id}/approve, /conflicts/{id}/reject."""
    client = TestClient(app)

    # 1. Check/Register a conflict via REST API
    resp_check = client.post("/conflicts/check", json={
        "claim": "Planning to switch database to CockroachDB.",
        "source_actor": "agent-cloud",
        "trust_level": 0.6
    })
    assert resp_check.status_code == 200
    data = resp_check.json()
    assert data["conflict_detected"] is True
    cid = data["conflict"]["conflict_id"]

    # 2. List pending conflicts
    resp_list = client.get("/conflicts/pending")
    assert resp_list.status_code == 200
    pending = resp_list.json()["pending_conflicts"]
    assert any(c["conflict_id"] == cid for c in pending)

    # 3. Agent attempts approval -> 403 Forbidden
    resp_unauth = client.post(f"/conflicts/{cid}/approve", json={
        "approver": "agent-cloud",
        "is_human": False,
        "decision": "approved"
    })
    assert resp_unauth.status_code == 403

    # 4. Human rejects conflict -> 200 OK
    resp_reject = client.post(f"/conflicts/{cid}/reject", json={
        "approver": "HumanAdmin",
        "is_human": True,
        "decision": "rejected",
        "rationale": "CockroachDB is not approved for this workload"
    })
    assert resp_reject.status_code == 200
    assert resp_reject.json()["status"] == "rejected"


def test_mcp_conflict_tools(pg):
    """Verify FastMCP tools for conflict management."""
    # Check conflict
    res_chk = memory_check_conflict(
        claim="Probably migrate from PostgreSQL to DynamoDB.",
        source_actor="agent-nosql"
    )
    assert res_chk["conflict_detected"] is True
    cid = res_chk["conflict"]["conflict_id"]

    # List conflicts
    confs = memory_conflicts_list()
    assert any(c["conflict_id"] == cid for c in confs)

    # Submit clarification via MCP
    res_clar = memory_conflict_clarify(
        conflict_id=cid,
        author="DevOpsLead",
        clarification_notes="Evaluation only, no migration planned."
    )
    assert res_clar["conflict_id"] == cid

    # Human reject via MCP
    res_rej = memory_conflict_reject(
        conflict_id=cid,
        approver="CTO_Tanish",
        rationale="DynamoDB does not meet ACID relational criteria",
        is_human=True
    )
    assert res_rej["status"] == "rejected"
