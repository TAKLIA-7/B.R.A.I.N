import uuid
import pytest
from core.adapters.postgres import PostgresAdapter
from core.bugs.manager import BugManager
from core.handoff.schemas import (
    CheckpointState,
    CheckpointStep,
    CheckpointDecision,
    RejectedApproach
)
from core.handoff.checkpoint import CheckpointService
from core.handoff.resume import ResumeService

def test_cross_agent_handover_scenario():
    """
    Executes the 12-step scenario from Section 12 of the Checkpoint Master Prompt:
    1. Agent A creates task AUTH-001.
    2. Agent A implements registration.
    3. Agent A implements login.
    4. Agent A records a database bug.
    5. Agent A records two failed attempts and one verified fix.
    6. Agent A saves checkpoint version 3.
    7. Simulate Agent A stopping.
    8. Agent B requests task resumption without Agent A transcript.
    9. Knowledge Brain retrieves checkpoint + debugging experience.
    10. Agent B implements refresh tokens.
    11. Agent B saves checkpoint version 4.
    12. Automated tests verify completion.
    """
    pg = PostgresAdapter()
    checkpoint_service = CheckpointService(postgres_adapter=pg)
    resume_service = ResumeService(postgres_adapter=pg)
    bug_manager = BugManager(postgres_adapter=pg)

    task_id = f"AUTH-001-{uuid.uuid4().hex[:6]}"
    bug_id = f"BUG-DB-{uuid.uuid4().hex[:6]}"
    fix_id = f"FIX-DB-{uuid.uuid4().hex[:6]}"

    # Step 1: Agent A creates task
    checkpoint_service.create_task(
        task_id=task_id,
        goal="Build FastAPI authentication system",
        created_by="Agent A"
    )

    # Step 2: Agent A implements registration (Checkpoint v1)
    state_v1 = CheckpointState(
        task_id=task_id,
        goal="Build FastAPI authentication system",
        steps=[
            CheckpointStep(id="registration", status="done", state="User registration implemented", evidence=["test_register passed"]),
            CheckpointStep(id="login", status="in_progress", state="Implementing JWT login", evidence=[]),
            CheckpointStep(id="refresh", status="pending", state="Pending refresh token", evidence=[])
        ],
        decisions=[CheckpointDecision(what="JWT Stateless Auth", why="Horizontal scalability", source="Agent A")],
        rejected=[RejectedApproach(option="Session cookies", reason="Requires stateful Redis store")],
        open_questions=["Which DB connection pool size?"],
        written_by="Agent A",
        project_files=["app/auth.py", "app/models.py"],
        test_results=["test_register passed"]
    )
    res_v1 = checkpoint_service.save_checkpoint(state_v1)
    assert res_v1["checkpoint_version"] == 1

    # Step 3: Agent A implements login (Checkpoint v2)
    state_v2 = CheckpointState(
        task_id=task_id,
        goal="Build FastAPI authentication system",
        steps=[
            CheckpointStep(id="registration", status="done", state="User registration implemented", evidence=["test_register passed"]),
            CheckpointStep(id="login", status="done", state="User login implemented", evidence=["test_login passed"]),
            CheckpointStep(id="refresh", status="pending", state="Pending refresh token", evidence=[])
        ],
        decisions=[CheckpointDecision(what="JWT Stateless Auth", why="Horizontal scalability", source="Agent A")],
        rejected=[RejectedApproach(option="Session cookies", reason="Requires stateful Redis store")],
        open_questions=["Which DB connection pool size?"],
        written_by="Agent A",
        project_files=["app/auth.py", "app/models.py"],
        test_results=["test_register passed", "test_login passed"]
    )
    res_v2 = checkpoint_service.save_checkpoint(state_v2)
    assert res_v2["checkpoint_version"] == 2

    # Step 4: Agent A records a database bug
    bug_manager.report_bug(
        bug_id=bug_id,
        title="Async DB connection pool exhausted under concurrent logins",
        symptom="psycopg2.OperationalError: connection pool exhausted",
        location={"files": ["app/auth.py", "app/db.py"]},
        severity="high",
        reported_by="Agent A"
    )

    # Step 5: Agent A records two failed attempts and one verified fix
    bug_manager.log_attempt(
        bug_id=bug_id,
        agent="Agent A",
        hypothesis="Increasing pool size to 50 will solve exhaustion",
        action="pool_size = 50",
        outcome="failed",
        learned="Exceeds max allowed connections in PostgreSQL"
    )
    bug_manager.log_attempt(
        bug_id=bug_id,
        agent="Agent A",
        hypothesis="Disable pool and use single connection",
        action="pool_size = 1",
        outcome="failed",
        learned="Causes massive latency bottleneck under load"
    )
    bug_manager.record_fix(
        fix_id=fix_id,
        bug_id=bug_id,
        commit="c-pool-fix-01",
        files_changed=["app/auth.py", "app/db.py"],
        summary="Implement async connection pooling with auto-recycling and context managers",
        verification={"result": "passed", "output": "100 concurrent logins completed in 0.4s without connection leaks"},
        fixed_by="Agent A"
    )

    # Step 6: Agent A saves checkpoint version 3 before stopping
    state_v3 = CheckpointState(
        task_id=task_id,
        goal="Build FastAPI authentication system",
        steps=[
            CheckpointStep(id="registration", status="done", state="User registration implemented", evidence=["test_register passed"]),
            CheckpointStep(id="login", status="done", state="User login implemented", evidence=["test_login passed"]),
            CheckpointStep(id="db_pool", status="done", state="Database connection pooling fixed", evidence=["Pool test passed"]),
            CheckpointStep(id="refresh", status="pending", state="Pending refresh token", evidence=[])
        ],
        decisions=[
            CheckpointDecision(what="JWT Stateless Auth", why="Horizontal scalability", source="Agent A"),
            CheckpointDecision(what="Connection pooling with context managers", why="Prevents cursor leaks", source="Agent A")
        ],
        rejected=[
            RejectedApproach(option="Session cookies", reason="Requires stateful Redis store"),
            RejectedApproach(option="Increase pool to 50", reason="Exceeds max PostgreSQL connection limit")
        ],
        open_questions=["Which refresh-token rotation strategy should be used?"],
        written_by="Agent A",
        project_files=["app/auth.py", "app/db.py"],
        test_results=["test_register passed", "test_login passed", "pool test passed"],
        git_commit="git-commit-agent-a-v3",
        git_branch="feature/auth-system"
    )
    res_v3 = checkpoint_service.save_checkpoint(state_v3)
    assert res_v3["checkpoint_version"] == 3

    # Step 7: Simulate Agent A stopping.
    # Step 8: Agent B requests task resumption (fresh session, zero transcript transfer).
    resume_context = resume_service.resume_task(
        task_id=task_id,
        requesting_agent="Agent B",
        token_budget=3000
    )

    # Step 9: Knowledge Brain retrieves checkpoint and relevant debugging experience
    assert resume_context.task_id == task_id
    assert resume_context.checkpoint_version == 3
    assert resume_context.previous_agent == "Agent A"
    assert resume_context.requesting_agent == "Agent B"
    assert len(resume_context.completed_steps) >= 3
    assert any("registration" in s.lower() for s in resume_context.completed_steps)
    assert any("login" in s.lower() for s in resume_context.completed_steps)
    assert any("refresh" in s.lower() for s in resume_context.pending_steps)

    # Verify bug and verified fix are present in Agent B's handover context
    assert len(resume_context.related_bugs) >= 1
    assert any(b["bug_id"] == bug_id for b in resume_context.related_bugs)
    assert len(resume_context.verified_fixes) >= 1
    assert any(f["fix_id"] == fix_id for f in resume_context.verified_fixes)

    # Step 10: Agent B continues and implements refresh tokens
    # Step 11: Agent B saves checkpoint version 4
    state_v4 = CheckpointState(
        task_id=task_id,
        goal="Build FastAPI authentication system",
        steps=[
            CheckpointStep(id="registration", status="done", state="User registration implemented", evidence=["test_register passed"]),
            CheckpointStep(id="login", status="done", state="User login implemented", evidence=["test_login passed"]),
            CheckpointStep(id="db_pool", status="done", state="Database connection pooling fixed", evidence=["Pool test passed"]),
            CheckpointStep(id="refresh", status="done", state="Refresh token rotation implemented", evidence=["test_refresh_token passed"])
        ],
        decisions=[
            CheckpointDecision(what="JWT Stateless Auth", why="Horizontal scalability", source="Agent A"),
            CheckpointDecision(what="Connection pooling with context managers", why="Prevents cursor leaks", source="Agent A"),
            CheckpointDecision(what="Sliding refresh token rotation", why="One-time use prevents replay attacks", source="Agent B")
        ],
        rejected=[
            RejectedApproach(option="Session cookies", reason="Requires stateful Redis store"),
            RejectedApproach(option="Increase pool to 50", reason="Exceeds max PostgreSQL connection limit"),
            RejectedApproach(option="Static non-expiring refresh token", reason="Vulnerable to token theft")
        ],
        open_questions=[],
        written_by="Agent B",
        project_files=["app/auth.py", "app/db.py", "app/refresh.py"],
        test_results=["test_register passed", "test_login passed", "pool test passed", "test_refresh_token passed"],
        git_commit="git-commit-agent-b-v4",
        git_branch="feature/auth-system"
    )
    res_v4 = checkpoint_service.save_checkpoint(state_v4)
    assert res_v4["checkpoint_version"] == 4
    assert res_v4["written_by"] == "Agent B"

    # Step 12: Automated tests verify the completed implementation and version progression
    final_status = checkpoint_service.get_task_status(task_id)
    assert final_status["latest_version"] == 4
    assert final_status["current_owner"] == "Agent B"

    all_checkpoints = checkpoint_service.get_checkpoint_history(task_id)
    assert len(all_checkpoints) == 4
    versions = [c["version"] for c in all_checkpoints]
    assert versions == [1, 2, 3, 4]
