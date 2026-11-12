import uuid
import pytest
from core.adapters.postgres import PostgresAdapter
from core.handoff.schemas import (
    CheckpointState,
    CheckpointStep,
    CheckpointDecision,
    RejectedApproach
)
from core.handoff.checkpoint import CheckpointService
from core.handoff.resume import ResumeService

@pytest.fixture
def pg():
    return PostgresAdapter()

@pytest.fixture
def checkpoint_service(pg):
    return CheckpointService(postgres_adapter=pg)

@pytest.fixture
def resume_service(pg):
    return ResumeService(postgres_adapter=pg)

def test_save_and_retrieve_checkpoint_versions(checkpoint_service, pg):
    task_id = f"task-db-{uuid.uuid4().hex[:6]}"

    # Version 1
    state_v1 = CheckpointState(
        task_id=task_id,
        goal="Build user auth",
        steps=[CheckpointStep(id="s1", status="done", state="Setup schema", evidence=["Schema migrated"])],
        decisions=[CheckpointDecision(what="Postgres", why="Durable", source="Agent A")],
        rejected=[RejectedApproach(option="Mongo", reason="No ACID")],
        open_questions=["Which hash algorithm?"],
        written_by="Agent A",
        project_files=["app/db.py"],
        test_results=["Schema test passed"],
        git_commit="c001",
        git_branch="main"
    )
    res_v1 = checkpoint_service.save_checkpoint(state_v1)
    assert res_v1["success"] is True
    assert res_v1["checkpoint_version"] == 1
    assert res_v1["written_by"] == "Agent A"

    # Version 2
    state_v2 = CheckpointState(
        task_id=task_id,
        goal="Build user auth",
        steps=[
            CheckpointStep(id="s1", status="done", state="Setup schema", evidence=["Schema migrated"]),
            CheckpointStep(id="s2", status="done", state="Password hashing", evidence=["bcrypt test passed"])
        ],
        decisions=[
            CheckpointDecision(what="Postgres", why="Durable", source="Agent A"),
            CheckpointDecision(what="bcrypt", why="Industry standard", source="Agent A")
        ],
        rejected=[RejectedApproach(option="Mongo", reason="No ACID")],
        open_questions=[],
        written_by="Agent A",
        project_files=["app/db.py", "app/security.py"],
        test_results=["Hash tests passed"],
        git_commit="c002",
        git_branch="main"
    )
    res_v2 = checkpoint_service.save_checkpoint(state_v2)
    assert res_v2["success"] is True
    assert res_v2["checkpoint_version"] == 2

    # Verify both versions exist in database
    history = checkpoint_service.get_checkpoint_history(task_id)
    assert len(history) == 2
    assert history[0]["version"] == 1
    assert history[1]["version"] == 2

    # Verify task ownership and status
    status_info = checkpoint_service.get_task_status(task_id)
    assert status_info["status"] == "in_progress"
    assert status_info["current_owner"] == "Agent A"
    assert status_info["latest_version"] == 2

def test_concurrency_detection(checkpoint_service):
    task_id = f"task-conflict-{uuid.uuid4().hex[:6]}"
    state = CheckpointState(
        task_id=task_id,
        goal="Test concurrency",
        steps=[],
        decisions=[],
        rejected=[],
        open_questions=[],
        written_by="Agent A"
    )
    res1 = checkpoint_service.save_checkpoint(state)
    assert res1["checkpoint_version"] == 1

    # Agent B tries to checkpoint expecting version 1 to still be the base
    # But if an expected_version constraint is violated:
    with pytest.raises(ValueError) as exc:
        checkpoint_service.save_checkpoint(state, expected_version=0)
    assert "Concurrency conflict" in str(exc.value)

def test_resume_service_with_bugs_and_fixes(checkpoint_service, resume_service, pg):
    task_id = f"task-handover-{uuid.uuid4().hex[:6]}"
    bug_id = f"BUG-{uuid.uuid4().hex[:6]}"
    fix_id = f"FIX-{uuid.uuid4().hex[:6]}"

    # Seed bug and fix in PostgreSQL
    with pg.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bugs (bug_id, title, symptom, root_cause, status, severity, location)
                VALUES (%s, 'JWT expiration off-by-one', 'Token expires immediately', 'Timezone UTC mismatch', 'fixed', 'high', '{"files": ["app/jwt.py"]}'::jsonb)
                ON CONFLICT (bug_id) DO NOTHING;
            """, (bug_id,))
            cur.execute("""
                INSERT INTO fixes (fix_id, bug_id, summary, fixed_by, verification)
                VALUES (%s, %s, 'Use datetime.now(timezone.utc)', 'Agent A', '{"result": "passed", "output": "Tokens now valid for 1 hour"}'::jsonb)
                ON CONFLICT (fix_id) DO NOTHING;
            """, (fix_id, bug_id))

    # Save checkpoint referencing the file app/jwt.py
    state = CheckpointState(
        task_id=task_id,
        goal="Build JWT authentication",
        steps=[
            CheckpointStep(id="jwt", status="done", state="JWT generation fixed", evidence=["Token expiration verified"]),
            CheckpointStep(id="refresh", status="pending", state="Pending refresh token", evidence=[])
        ],
        decisions=[CheckpointDecision(what="JWT", why="Stateless", source="Agent A")],
        rejected=[RejectedApproach(option="Session cookies", reason="Stateless required")],
        open_questions=["Rotation strategy?"],
        written_by="Agent A",
        project_files=["app/jwt.py"]
    )
    checkpoint_service.save_checkpoint(state)

    # Resume task for Agent B
    handover = resume_service.resume_task(
        task_id=task_id,
        requesting_agent="Agent B",
        token_budget=2000
    )

    assert handover.task_id == task_id
    assert handover.previous_agent == "Agent A"
    assert handover.requesting_agent == "Agent B"
    assert "JWT generation fixed" in handover.completed_steps[0]
    assert "Pending refresh token" in handover.pending_steps[0]
    assert len(handover.related_bugs) >= 1
    assert any(b.get("bug_id") == bug_id for b in handover.related_bugs)
    assert len(handover.verified_fixes) >= 1
    assert any(f.get("fix_id") == fix_id for f in handover.verified_fixes)

