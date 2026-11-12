import pytest
from pydantic import ValidationError
from core.models.checkpoint import (
    HandoverState,
    StepItem,
    StepStatus,
    DecisionItem,
    RejectedOption
)

def test_valid_handover_state():
    state = HandoverState(
        task_id="task-fastapi-001",
        goal="Build FastAPI Task Management REST API",
        steps=[
            StepItem(
                id="step-1",
                status=StepStatus.DONE,
                state="Created project scaffold and requirements",
                evidence=["requirements.txt exists", "tests pass"]
            ),
            StepItem(
                id="step-2",
                status=StepStatus.IN_PROGRESS,
                state="Implementing CRUD endpoints",
                evidence=[]
            ),
            StepItem(
                id="step-3",
                status=StepStatus.PENDING,
                state="Write unit and integration tests",
                evidence=[]
            )
        ],
        decisions=[
            DecisionItem(
                what="Use Pydantic v2 for request validation",
                why="Strict schema safety and fast JSON parsing",
                source="architectural invariant"
            )
        ],
        rejected=[
            RejectedOption(
                option="Flask RESTful",
                reason="Lacks native async support and auto OpenAPI generation"
            )
        ],
        open_questions=["Which auth middleware should be used?"],
        written_by="agent-antigravity"
    )
    assert state.task_id == "task-fastapi-001"
    assert state.steps[0].status == StepStatus.DONE
    assert len(state.decisions) == 1
    assert len(state.rejected) == 1

def test_invalid_step_status_rejected():
    with pytest.raises(ValidationError):
        StepItem(
            id="step-1",
            status="finished",  # must be 'done', 'in_progress', or 'pending'
            state="Done something"
        )

def test_arbitrary_extra_fields_rejected():
    with pytest.raises(ValidationError):
        HandoverState(
            task_id="task-002",
            goal="Test extra fields",
            steps=[],
            decisions=[],
            rejected=[],
            open_questions=[],
            written_by="agent",
            hallucinated_field="forbidden"  # extra='forbid'
        )

def test_missing_required_fields_rejected():
    with pytest.raises(ValidationError):
        HandoverState(
            task_id="task-003",
            goal="Incomplete checkpoint"
            # Missing steps, decisions, rejected, open_questions, written_by
        )

