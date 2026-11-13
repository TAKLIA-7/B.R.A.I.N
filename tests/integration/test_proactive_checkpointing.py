"""
tests/integration/test_proactive_checkpointing.py
Comprehensive integration tests for Proactive AI Agent Checkpointing:
- CheckpointScheduler workflow & Mode A/B
- Canonical PostgreSQL persistence & audit logging
- Automatic checkpoint.md creation and history preservation
- Concurrency, conflict detection, and independent agent resumption
- REST API and MCP tool verification
"""
import os
import uuid
import pytest
from fastapi.testclient import TestClient
from core.adapters.postgres import PostgresAdapter
from core.handoff.checkpoint import CheckpointService
from core.handoff.resume import ResumeService
from core.handoff.schemas import CheckpointState, CheckpointStep, CheckpointDecision
from core.project_knowledge.manager import ProjectKnowledgeManager
from core.project_knowledge.schemas import ProjectCreateRequest
from core.project_knowledge.synchronizer import ProjectDocumentSynchronizer
from core.agent_monitor.base_adapter import AgentUsageMetrics
from core.agent_monitor.checkpoint_scheduler import CheckpointScheduler
from core.agent_monitor.usage_monitor import CheckpointPolicy, UsageMonitor
from api import app
from mcp_server import agent_report_usage, agent_trigger_checkpoint, task_checkpoint


@pytest.fixture
def pg_adapter():
    return PostgresAdapter()


@pytest.fixture
def test_project(pg_adapter):
    """Registers a fresh test project."""
    p_id = f"test-proj-{uuid.uuid4().hex[:6]}"
    manager = ProjectKnowledgeManager(postgres_adapter=pg_adapter)
    req = ProjectCreateRequest(
        id=p_id,
        name=f"Proactive Test Project {p_id}",
        description="Integration testing project for proactive checkpoints"
    )
    p = manager.register_project(req)
    yield p
    # Teardown
    import shutil
    sync = ProjectDocumentSynchronizer(postgres_adapter=pg_adapter)
    pdir = sync.get_project_dir(p_id)
    if os.path.exists(pdir):
        shutil.rmtree(pdir, ignore_errors=True)
    try:
        pg_adapter.execute_query("DELETE FROM projects WHERE id = %s;", (p_id,))
    except Exception:
        pass


def test_scheduler_proactive_execution(pg_adapter, test_project):
    """Verify end-to-end execution of proactive checkpointing."""
    p_id = test_project.id
    task_id = f"{p_id}-task-1"

    scheduler = CheckpointScheduler(postgres_adapter=pg_adapter)
    state = CheckpointState(
        task_id=task_id,
        goal="Develop Proactive Checkpointing Unit",
        steps=[
            CheckpointStep(id="step-1", status="done", state="Setup database tables"),
            CheckpointStep(id="step-2", status="in_progress", state="Integrate scheduler"),
            CheckpointStep(id="step-3", status="pending", state="Verify markdown output")
        ],
        decisions=[
            CheckpointDecision(what="Store in Postgres first", why="ACID reliability", source="ADR-001")
        ],
        rejected=[],
        written_by="antigravity",
        project_files=["core/agent_monitor/checkpoint_scheduler.py"]
    )

    metrics = AgentUsageMetrics(
        agent_name="antigravity",
        task_id=task_id,
        tokens_consumed=820000,
        context_window_capacity=1000000
    )

    # Execute checkpoint
    result = scheduler.execute_checkpoint(
        task_id=task_id,
        state=state,
        project_id=p_id,
        trigger_reason="threshold_80_auto",
        agent_name="antigravity",
        metrics=metrics
    )

    assert result["success"] is True
    assert result["task_id"] == task_id
    assert result["project_id"] == p_id
    assert result["checkpoint_version"] >= 1
    assert result["markdown_synced"] is True

    # 1. Verify PostgreSQL persistence (Authoritative source of truth)
    cp_rows = pg_adapter.execute_query(
        "SELECT version, state_json, written_by FROM checkpoints WHERE task_id = %s ORDER BY version DESC;",
        (task_id,)
    )
    assert len(cp_rows) >= 1
    assert cp_rows[0]["written_by"] == "antigravity"

    # Verify audit trigger was logged
    audit_rows = pg_adapter.execute_query(
        "SELECT trigger_reason, context_percentage, status FROM checkpoint_triggers WHERE task_id = %s;",
        (task_id,)
    )
    assert len(audit_rows) >= 1
    assert audit_rows[0]["trigger_reason"] == "threshold_80_auto"
    assert float(audit_rows[0]["context_percentage"]) == 82.0

    # 2. Verify on-disk checkpoint.md was generated
    sync = ProjectDocumentSynchronizer(postgres_adapter=pg_adapter)
    pdir = sync.get_project_dir(p_id)
    cp_path = os.path.join(pdir, "checkpoint.md")
    assert os.path.exists(cp_path)

    with open(cp_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert f"# Project Checkpoint:" in content
    assert f"`{task_id}`" in content
    assert "Setup database tables" in content
    assert "Integrate scheduler" in content
    assert "Store in Postgres first" in content

    # 3. Verify history preservation: checkpoints/checkpoint_v1.md
    v = result["checkpoint_version"]
    hist_path = os.path.join(pdir, "checkpoints", f"checkpoint_v{v}.md")
    assert os.path.exists(hist_path)


def test_conflict_detection_on_manual_edits(pg_adapter, test_project):
    """Verify that manual human edits to checkpoint.md trigger conflict status rather than silent overwriting."""
    p_id = test_project.id
    task_id = f"{p_id}-conflict-task"

    scheduler = CheckpointScheduler(postgres_adapter=pg_adapter)
    state = CheckpointState(
        task_id=task_id,
        goal="Conflict testing",
        steps=[CheckpointStep(id="s1", status="done", state="Init")],
        decisions=[],
        rejected=[],
        written_by="agent"
    )

    # Initial checkpoint writes checkpoint.md
    res1 = scheduler.execute_checkpoint(task_id=task_id, state=state, project_id=p_id)
    assert res1["success"] is True

    # Simulate human developer manually modifying checkpoint.md on disk
    sync = ProjectDocumentSynchronizer(postgres_adapter=pg_adapter)
    cp_path = os.path.join(sync.get_project_dir(p_id), "checkpoint.md")
    with open(cp_path, "w", encoding="utf-8") as f:
        f.write("# Human Manual Edits\nDeveloper custom notes that must not be silently wiped.\n")

    # Second checkpoint attempt without force detects conflict
    state.steps.append(CheckpointStep(id="s2", status="done", state="Second step"))
    res2 = scheduler.execute_checkpoint(task_id=task_id, state=state, project_id=p_id)
    assert res2["markdown_status"] == "conflict"

    # Human content was preserved on disk!
    with open(cp_path, "r", encoding="utf-8") as f:
        disk_content = f.read()
    assert "# Human Manual Edits" in disk_content


def test_independent_agent_task_resumption(pg_adapter, test_project):
    """Verify an independent fresh agent can resume the task using task_resume."""
    p_id = test_project.id
    task_id = f"{p_id}-resume-task"

    scheduler = CheckpointScheduler(postgres_adapter=pg_adapter)
    state = CheckpointState(
        task_id=task_id,
        goal="Build JWT authentication filter",
        steps=[
            CheckpointStep(id="step-1", status="done", state="Added PyJWT requirement"),
            CheckpointStep(id="step-2", status="pending", state="Implement decode token middleware")
        ],
        decisions=[
            CheckpointDecision(what="Use RS256 algorithm", why="Asymmetric signing security", source="Security Spec")
        ],
        rejected=[],
        written_by="original-agent-antigravity"
    )

    # Checkpoint saved
    scheduler.execute_checkpoint(task_id=task_id, state=state, project_id=p_id)

    # Independent agent resumes task
    resume_service = ResumeService(postgres_adapter=pg_adapter)
    resumption = resume_service.resume_task(task_id=task_id, requesting_agent="new-agent-codex")

    assert resumption.task_id == task_id
    assert resumption.previous_agent == "original-agent-antigravity"
    assert resumption.requesting_agent == "new-agent-codex"
    assert "Added PyJWT requirement" in resumption.completed_steps
    assert "Implement decode token middleware" in resumption.pending_steps
    assert "RS256" in resumption.handover_context


def test_concurrent_checkpoint_safety(pg_adapter, test_project):
    """Verify concurrent checkpoint attempts are handled safely with locks."""
    import concurrent.futures

    p_id = test_project.id
    task_id = f"{p_id}-concurrency-task"
    scheduler = CheckpointScheduler(postgres_adapter=pg_adapter)

    def run_cp(idx):
        st = CheckpointState(
            task_id=task_id,
            goal=f"Concurrency run {idx}",
            steps=[CheckpointStep(id=f"step-{idx}", status="done", state=f"Completed {idx}")],
            decisions=[],
            rejected=[],
            written_by=f"agent-{idx}"
        )
        return scheduler.execute_checkpoint(task_id=task_id, state=st, project_id=p_id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_cp, i) for i in range(3)]
        results = [f.result() for f in futures]

    assert all(r["success"] is True for r in results)
    # Check that versions strictly incremented
    versions = [r["checkpoint_version"] for r in results]
    assert len(set(versions)) == 3  # All versions must be unique


def test_rest_api_endpoints(pg_adapter, test_project):
    """Verify REST API /agent/usage, /agent/checkpoint/proactive, and /agent/checkpoint/triggers."""
    client = TestClient(app)
    p_id = test_project.id
    task_id = f"{p_id}-api-task"

    # 1. Report usage at 82% (threshold 80% auto triggers checkpoint)
    resp = client.post("/agent/usage", json={
        "agent_name": "antigravity",
        "task_id": task_id,
        "project_id": p_id,
        "tokens_consumed": 82000,
        "context_window_capacity": 100000,
        "auto_checkpoint": True
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["triggered"] is True
    assert data["usage_percentage"] == 82.0

    # 2. Get triggers audit log
    resp_triggers = client.get(f"/agent/checkpoint/triggers/{task_id}")
    assert resp_triggers.status_code == 200
    triggers = resp_triggers.json()["triggers"]
    assert len(triggers) >= 1

    # 3. Trigger proactive checkpoint directly
    resp_pro = client.post("/agent/checkpoint/proactive", json={
        "task_id": task_id,
        "project_id": p_id,
        "trigger_reason": "manual_test",
        "agent_name": "codex"
    })
    assert resp_pro.status_code == 200
    assert resp_pro.json()["success"] is True


def test_mcp_tools(pg_adapter, test_project):
    """Verify agent_report_usage and agent_trigger_checkpoint MCP tools."""
    p_id = test_project.id
    task_id = f"{p_id}-mcp-task"

    # Report usage via MCP tool
    res = agent_report_usage(
        agent_name="antigravity",
        tokens_consumed=850000,
        context_window_capacity=1000000,
        task_id=task_id,
        project_id=p_id,
        auto_checkpoint=True
    )
    assert res["triggered"] is True
    assert res["usage_percentage"] == 85.0

    # Explicit trigger via MCP tool
    res_trigger = agent_trigger_checkpoint(
        task_id=task_id,
        project_id=p_id,
        trigger_reason="developer_explicit",
        agent_name="antigravity"
    )
    assert res_trigger["success"] is True
    assert res_trigger["checkpoint_version"] >= 1

