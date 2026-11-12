import pytest
from scripts.run_thirty_sessions import run_thirty_sessions

def test_thirty_session_scenario():
    """
    Executes the full 30-session deterministic scenario including mid-run restart,
    planted false claim, memory conflict, checkpoint/resume, verified forgetting,
    and bug intelligence lifecycle.
    """
    metrics = run_thirty_sessions(restart_enabled=True)
    assert metrics["total_sessions"] == 30
    assert metrics["all_verifications_passed"] is True
    assert metrics["verifications"]["planted_claim_asserted"] is True
    assert metrics["verifications"]["redis_ttl_active"] is True
    assert metrics["verifications"]["superseded_history_preserved"] is True
    assert metrics["verifications"]["task_resumed_post_restart"] is True
    assert metrics["verifications"]["memories_survived_restart"] is True
    assert metrics["verifications"]["three_checkpoint_versions_exist"] is True
    assert metrics["verifications"]["deletion_verified"] is True
    assert metrics["verifications"]["bug_fix_verified"] is True
    assert metrics["verifications"]["markdown_projections_synced"] is True
    assert metrics["verifications"]["abstention_honored"] is True
    assert metrics["verifications"]["bug_history_retrieved"] is True

