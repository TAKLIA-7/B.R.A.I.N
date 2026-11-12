import pytest
from pydantic import ValidationError
from core.handoff.schemas import (
    CheckpointStep,
    CheckpointDecision,
    RejectedApproach,
    CheckpointState,
    ResumeRequest,
    ResumeResponse
)
from core.handoff.versioning import VersionManager

def test_valid_checkpoint_state():
    state = CheckpointState(
        task_id="AUTH-001",
        goal="Build FastAPI authentication",
        steps=[
            CheckpointStep(
                id="registration",
                status="done",
                state="Registration implemented",
                evidence=["Registration tests passed"]
            ),
            CheckpointStep(
                id="refresh-token",
                status="pending",
                state="Not implemented",
                evidence=[]
            )
        ],
        decisions=[
            CheckpointDecision(
                what="Use JWT authentication",
                why="Stateless authentication",
                source="Agent A"
            )
        ],
        rejected=[
            RejectedApproach(
                option="Session-based authentication",
                reason="Not selected for this implementation"
            )
        ],
        open_questions=["Which refresh-token rotation strategy should be used?"],
        written_by="Agent A",
        project_files=["app/auth.py"],
        test_results=["Registration tests passed"],
        git_commit="a1b2c3d4",
        git_branch="feature/auth"
    )

    assert state.task_id == "AUTH-001"
    assert len(state.steps) == 2
    assert state.steps[0].status == "done"
    assert state.steps[1].status == "pending"
    assert state.decisions[0].what == "Use JWT authentication"
    assert state.rejected[0].option == "Session-based authentication"
    assert state.git_commit == "a1b2c3d4"
    assert state.git_branch == "feature/auth"

def test_checkpoint_state_rejects_extra_fields():
    with pytest.raises(ValidationError):
        CheckpointState(
            task_id="AUTH-001",
            goal="Build auth",
            steps=[],
            decisions=[],
            rejected=[],
            open_questions=[],
            written_by="Agent A",
            unexpected_field="hallucinated_data"
        )

def test_invalid_step_status_rejected():
    with pytest.raises(ValidationError):
        CheckpointStep(
            id="step-1",
            status="finished_completely",  # Must be "done" | "in_progress" | "pending"
            state="Done",
            evidence=[]
        )

def test_missing_required_fields_rejected():
    with pytest.raises(ValidationError):
        CheckpointState(
            task_id="AUTH-001"
            # Missing goal, steps, decisions, rejected, open_questions, written_by
        )

def test_resume_response_structure():
    response = ResumeResponse(
        task_id="AUTH-001",
        checkpoint_version=3,
        previous_agent="Agent A",
        requesting_agent="Agent B",
        completed_steps=["Registration implemented", "Login implemented"],
        pending_steps=["Refresh-token implementation"],
        decisions=["Use JWT authentication"],
        rejected_approaches=["Session-based authentication"],
        related_bugs=[],
        verified_fixes=[],
        open_questions=["Choose refresh-token rotation strategy"],
        handover_context="Compact context assembled for Agent B"
    )
    assert response.checkpoint_version == 3
    assert response.previous_agent == "Agent A"
    assert len(response.completed_steps) == 2
    assert response.pending_steps == ["Refresh-token implementation"]

