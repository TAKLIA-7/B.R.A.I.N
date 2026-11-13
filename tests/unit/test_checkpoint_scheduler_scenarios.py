"""
tests/unit/test_checkpoint_scheduler_scenarios.py
Unit tests for edge cases:
- Missing usage telemetry and fallback modes
- Agent crash and retry scenarios
- Idempotency key handling and deduplication
- Mode A (agent-assisted) vs Mode B (host-side automated)
"""
import pytest
from unittest.mock import MagicMock
from core.agent_monitor.base_adapter import AgentUsageMetrics, TriggerReason
from core.agent_monitor.usage_monitor import UsageMonitor, CheckpointPolicy
from core.agent_monitor.checkpoint_scheduler import CheckpointScheduler
from core.handoff.schemas import CheckpointState, CheckpointStep


def test_agent_crash_recovery_and_retry():
    """
    Test scenario: Agent crashes midway or database raises a transient error.
    Scheduler guarantees idempotency and safe recovery on subsequent attempts.
    """
    mock_pg = MagicMock()
    mock_cp_svc = MagicMock()
    mock_sync = MagicMock()
    mock_sync.get_project_dir.return_value = "/tmp/fake-proj"
    mock_sync.sync_document.return_value = (True, "synced")

    scheduler = CheckpointScheduler(
        postgres_adapter=mock_pg,
        checkpoint_service=mock_cp_svc,
        synchronizer=mock_sync
    )

    state = CheckpointState(
        task_id="crash-task",
        goal="Crash recovery test",
        steps=[CheckpointStep(id="s1", status="done", state="Init step")],
        decisions=[],
        rejected=[],
        written_by="crashing-agent"
    )

    # First attempt: Database fails transiently (e.g. timeout / connection blip)
    mock_cp_svc.save_checkpoint.side_effect = RuntimeError("Transient DB connection drop")

    with pytest.raises(RuntimeError, match="Transient DB connection drop"):
        scheduler.execute_checkpoint(task_id="crash-task", state=state, project_id="proj-crash")

    # Second attempt: Database succeeds on retry
    mock_cp_svc.save_checkpoint.side_effect = None
    mock_cp_svc.save_checkpoint.return_value = {
        "success": True,
        "checkpoint_version": 2,
        "task_id": "crash-task"
    }

    res = scheduler.execute_checkpoint(
        task_id="crash-task",
        state=state,
        project_id="proj-crash",
        idempotency_key="crash-task:retry:1"
    )

    assert res["success"] is True
    assert res["checkpoint_version"] == 2
    assert mock_sync.sync_document.call_count == 2  # checkpoint.md and checkpoints/checkpoint_v2.md


def test_host_side_mode_b_state_recovery():
    """
    Test Mode B: Host triggers checkpoint when agent is unaware.
    Scheduler recovers latest known state from checkpoint_service.
    """
    mock_pg = MagicMock()
    mock_cp_svc = MagicMock()
    mock_sync = MagicMock()
    mock_sync.get_project_dir.return_value = "/tmp/fake-proj"
    mock_sync.sync_document.return_value = (True, "synced")

    # Mock existing state in Postgres
    mock_cp_svc.get_latest_checkpoint.return_value = {
        "id": "cp-uuid-1",
        "task_id": "mode-b-task",
        "version": 3,
        "state_json": {
            "task_id": "mode-b-task",
            "goal": "Host side automated checkpoint",
            "steps": [{"id": "s1", "status": "done", "state": "Finished", "evidence": []}],
            "decisions": [],
            "rejected": [],
            "open_questions": [],
            "written_by": "agent-host",
            "project_files": [],
            "test_results": []
        },
        "written_by": "agent-host"
    }
    mock_cp_svc.save_checkpoint.return_value = {
        "success": True,
        "checkpoint_version": 4,
        "task_id": "mode-b-task"
    }

    scheduler = CheckpointScheduler(
        postgres_adapter=mock_pg,
        checkpoint_service=mock_cp_svc,
        synchronizer=mock_sync
    )

    # Execute without explicit state (Mode B)
    res = scheduler.execute_checkpoint(
        task_id="mode-b-task",
        project_id="proj-b",
        trigger_reason="event_compaction_imminent"
    )

    assert res["success"] is True
    assert res["checkpoint_version"] == 4
    # State was recovered from checkpoint_service.get_latest_checkpoint
    assert mock_cp_svc.get_latest_checkpoint.called


def test_missing_telemetry_does_not_invent_tokens():
    """Verify missing usage telemetry produces unknown metrics and does NOT hallucinate tokens."""
    monitor = UsageMonitor()
    adapter = monitor.get_adapter("antigravity")

    # Collecting usage without parameters
    metrics = adapter.collect_usage(session_id="empty-sess", task_id="empty-task")
    assert metrics.tokens_consumed is None
    assert metrics.context_window_capacity is not None  # known for default model
    assert metrics.get_effective_usage_percentage() is None
    assert metrics.is_context_percentage_known() is False
    assert metrics.source == "unknown"


def test_custom_configurable_policies():
    """Verify policies are fully configurable."""
    custom_policy = CheckpointPolicy(
        prepare_threshold=50.0,
        auto_checkpoint_threshold=60.0,
        urgent_threshold=75.0,
        critical_threshold=85.0,
        cooldown_seconds=15
    )
    monitor = UsageMonitor(policy=custom_policy)

    m = AgentUsageMetrics(agent_name="antigravity", usage_percentage=62.0)
    assert monitor.evaluate_metrics(m) == TriggerReason.THRESHOLD_80_AUTO  # triggered auto because >= 60%

