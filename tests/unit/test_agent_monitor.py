"""
tests/unit/test_agent_monitor.py
Comprehensive unit tests for Agent Usage Monitoring, Adapters, Threshold Evaluation,
Git Inspection, and Checkpoint Markdown Generation.
"""
import pytest
from datetime import datetime, timezone
from core.agent_monitor.base_adapter import (
    AgentUsageMetrics,
    TriggerReason
)
from core.agent_monitor.antigravity_adapter import (
    AntigravityAdapter,
    ANTIGRAVITY_MODEL_CAPACITIES
)
from core.agent_monitor.codex_adapter import (
    CodexAdapter,
    CODEX_MODEL_CAPACITIES
)
from core.agent_monitor.usage_monitor import (
    UsageMonitor,
    CheckpointPolicy
)
from core.agent_monitor.git_inspector import GitInspector, GitWorkingTreeState
from core.agent_monitor.checkpoint_generator import CheckpointMarkdownGenerator
from core.handoff.schemas import CheckpointState, CheckpointStep, CheckpointDecision, RejectedApproach


def test_usage_percentage_calculation():
    """Verify exact percentage calculations and boundary handling."""
    # 1. Direct percentage provided
    m1 = AgentUsageMetrics(agent_name="test", usage_percentage=82.5)
    assert m1.is_context_percentage_known() is True
    assert m1.get_effective_usage_percentage() == 82.5

    # 2. Calculated from tokens and capacity
    m2 = AgentUsageMetrics(
        agent_name="test",
        tokens_consumed=80000,
        context_window_capacity=100000
    )
    assert m2.is_context_percentage_known() is True
    assert m2.get_effective_usage_percentage() == 80.0
    assert m2.get_remaining_capacity() == 20000

    # 3. Missing tokens -> unknown
    m3 = AgentUsageMetrics(agent_name="test", context_window_capacity=100000)
    assert m3.is_context_percentage_known() is False
    assert m3.get_effective_usage_percentage() is None
    assert m3.get_remaining_capacity() is None

    # 4. Zero capacity raises ValidationError (ge=1 constraint)
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AgentUsageMetrics(agent_name="test", tokens_consumed=5000, context_window_capacity=0)


def test_antigravity_adapter():
    """Verify Antigravity adapter token handling, model lookups, and notifications."""
    adapter = AntigravityAdapter()
    assert adapter.get_agent_name() == "antigravity"
    assert adapter.lookup_model_capacity("gemini-3.8-flash") == 1048576
    assert adapter.lookup_model_capacity("claude-3-5-sonnet") == 200000
    assert adapter.lookup_model_capacity("unknown-model-xyz") is None

    # Collect usage with explicit parameters
    metrics = adapter.collect_usage(
        session_id="session-123",
        task_id="task-456",
        model_name="claude-3-5-sonnet",
        tokens_consumed=160000
    )
    assert metrics.agent_name == "antigravity"
    assert metrics.context_window_capacity == 200000
    assert metrics.tokens_consumed == 160000
    assert metrics.get_effective_usage_percentage() == 80.0

    # Notification buffer
    res = adapter.notify_agent(warning_level="urgent", message="Context at 90%", task_id="task-456")
    assert res is True
    assert len(adapter.notifications) == 1
    assert adapter.notifications[0]["warning_level"] == "urgent"


def test_codex_adapter():
    """Verify OpenAI Codex adapter API response parsing and capacity mappings."""
    adapter = CodexAdapter()
    assert adapter.get_agent_name() == "codex"
    assert adapter.lookup_model_capacity("gpt-4o") == 128000
    assert adapter.lookup_model_capacity("o1") == 200000

    # Collect usage from simulated OpenAI API usage dict
    api_usage = {"total_tokens": 102400, "prompt_tokens": 100000, "completion_tokens": 2400}
    metrics = adapter.collect_usage(
        session_id="codex-sess-1",
        task_id="task-codex",
        model_name="gpt-4o",
        api_usage=api_usage
    )
    assert metrics.tokens_consumed == 102400
    assert metrics.context_window_capacity == 128000
    assert metrics.get_effective_usage_percentage() == 80.0
    assert metrics.source == "sdk"


def test_threshold_based_checkpoint_triggering():
    """Verify policy thresholds: 70% prepare, 80% auto, 90% urgent, 95% critical."""
    policy = CheckpointPolicy(
        prepare_threshold=70.0,
        auto_checkpoint_threshold=80.0,
        urgent_threshold=90.0,
        critical_threshold=95.0,
        cooldown_seconds=0  # zero cooldown for direct step test
    )
    monitor = UsageMonitor(policy=policy)

    # Below 70% -> None
    m_60 = AgentUsageMetrics(agent_name="antigravity", task_id="task-t", usage_percentage=65.0)
    assert monitor.evaluate_metrics(m_60) is None

    # 70% -> THRESHOLD_70_PREPARE
    m_70 = AgentUsageMetrics(agent_name="antigravity", task_id="task-t", usage_percentage=72.0)
    assert monitor.evaluate_metrics(m_70) == TriggerReason.THRESHOLD_70_PREPARE

    # 80% -> THRESHOLD_80_AUTO
    m_80 = AgentUsageMetrics(agent_name="antigravity", task_id="task-t", usage_percentage=82.0)
    assert monitor.evaluate_metrics(m_80) == TriggerReason.THRESHOLD_80_AUTO

    # 90% -> THRESHOLD_90_URGENT
    m_90 = AgentUsageMetrics(agent_name="antigravity", task_id="task-t", usage_percentage=91.0)
    assert monitor.evaluate_metrics(m_90) == TriggerReason.THRESHOLD_90_URGENT

    # 95% -> THRESHOLD_95_CRITICAL
    m_95 = AgentUsageMetrics(agent_name="antigravity", task_id="task-t", usage_percentage=96.5)
    assert monitor.evaluate_metrics(m_95) == TriggerReason.THRESHOLD_95_CRITICAL


def test_duplicate_event_handling_and_cooldown():
    """Verify deduplication suppresses repeated events within cooldown."""
    policy = CheckpointPolicy(cooldown_seconds=300)
    monitor = UsageMonitor(policy=policy)

    m1 = AgentUsageMetrics(agent_name="antigravity", task_id="task-cd", usage_percentage=82.0)
    # First trigger succeeds
    res1 = monitor.evaluate_metrics(m1)
    assert res1 == TriggerReason.THRESHOLD_80_AUTO

    # Second trigger with same percentage within cooldown is suppressed
    m2 = AgentUsageMetrics(agent_name="antigravity", task_id="task-cd", usage_percentage=82.2)
    res2 = monitor.evaluate_metrics(m2)
    assert res2 is None

    # Escalation to urgent (91%) bypasses cooldown
    m3 = AgentUsageMetrics(agent_name="antigravity", task_id="task-cd", usage_percentage=91.0)
    res3 = monitor.evaluate_metrics(m3)
    assert res3 == TriggerReason.THRESHOLD_90_URGENT


def test_missing_usage_telemetry_fallback():
    """Verify missing usage telemetry activates fallback policy and is clearly identified."""
    policy = CheckpointPolicy(fallback_to_periodic=True, periodic_interval_seconds=10)
    monitor = UsageMonitor(policy=policy)

    # Missing telemetry metrics (all None)
    m_unknown = AgentUsageMetrics(agent_name="antigravity", task_id="task-fallback")
    assert m_unknown.is_context_percentage_known() is False

    # Immediate check with force=True triggers fallback
    res = monitor.evaluate_metrics(m_unknown, force=True)
    assert res == TriggerReason.FALLBACK_PERIODIC
    assert res != TriggerReason.THRESHOLD_80_AUTO


def test_lifecycle_event_triggers():
    """Verify explicit compaction and session ending events trigger appropriate reasons."""
    monitor = UsageMonitor()

    r1 = monitor.evaluate_lifecycle_event("compaction_imminent", task_id="task-evt")
    assert r1 == TriggerReason.EVENT_COMPACTION_IMMINENT

    r2 = monitor.evaluate_lifecycle_event("session_ending", task_id="task-evt")
    assert r2 == TriggerReason.EVENT_SESSION_END

    r3 = monitor.evaluate_lifecycle_event("task_boundary", task_id="task-evt")
    assert r3 == TriggerReason.FALLBACK_TASK_BOUNDARY


def test_checkpoint_markdown_generator_sections():
    """Verify all required sections A through H are generated in checkpoint.md."""
    state = CheckpointState(
        task_id="task-md-test",
        goal="Implement Stripe Webhook Verification",
        steps=[
            CheckpointStep(id="step-1", status="done", state="Configured Stripe endpoint", evidence=["api/webhooks.py"]),
            CheckpointStep(id="step-2", status="in_progress", state="Validating HMAC SHA-256 signature"),
            CheckpointStep(id="step-3", status="pending", state="Add unit tests")
        ],
        decisions=[
            CheckpointDecision(what="Use Stripe Webhook SDK", why="Ensures signature authenticity", source="ADR-004")
        ],
        rejected=[
            RejectedApproach(option="Plain JSON payload without signing secret", reason="Vulnerable to spoofing")
        ],
        open_questions=["Should webhook errors retry automatically?"],
        written_by="antigravity",
        project_files=["api/webhooks.py"],
        test_results=["pytest tests/test_webhooks.py: 2 passed"]
    )

    git_state = GitWorkingTreeState(
        branch="feature/webhooks",
        commit="a1b2c3d",
        files_created=["api/webhooks.py"],
        files_modified=["core/config.py"],
        files_deleted=[],
        uncommitted_changes_count=2,
        diff_summary="2 files changed, 45 insertions(+)",
        is_git_repo=True
    )

    bugs = [{"bug_id": "BUG-001", "title": "Invalid signature format", "severity": "high"}]
    fixes = [{"fix_id": "FIX-001", "summary": "Fixed raw body payload decoding"}]

    md = CheckpointMarkdownGenerator.generate_checkpoint_md(
        state=state,
        project_id="stripe-integration",
        project_name="Stripe Integration",
        checkpoint_version=3,
        trigger_reason="threshold_80_auto",
        session_id="session-xyz",
        git_state=git_state,
        bugs=bugs,
        fixes=fixes
    )

    # Verify sections A through H are present
    assert "# Project Checkpoint: Stripe Integration (`stripe-integration`)" in md
    assert "## A. Current Task" in md
    assert "`task-md-test`" in md
    assert "Implement Stripe Webhook Verification" in md

    assert "## B. Recent Changes" in md
    assert "`api/webhooks.py`" in md
    assert "`core/config.py`" in md

    assert "## C. Completed Work" in md
    assert "Configured Stripe endpoint" in md
    assert "pytest tests/test_webhooks.py: 2 passed" in md
    assert "FIX-001" in md

    assert "## D. Current Working State" in md
    assert "Validating HMAC SHA-256 signature" in md
    assert "`feature/webhooks`" in md
    assert "`a1b2c3d`" in md

    assert "## E. Decisions and Reasoning" in md
    assert "Use Stripe Webhook SDK" in md
    assert "Vulnerable to spoofing" in md

    assert "## F. Known Problems" in md
    assert "BUG-001" in md
    assert "Invalid signature format" in md

    assert "## G. Next Steps" in md
    assert "Add unit tests" in md

    assert "## H. Resumption Instructions" in md
    assert "task_resume(task_id='task-md-test')" in md
