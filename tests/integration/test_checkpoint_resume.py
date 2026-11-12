import pytest
import uuid
from pydantic import ValidationError
from core.models.checkpoint import (
    HandoverState,
    StepItem,
    StepStatus,
    DecisionItem,
    RejectedOption
)
from core.handoff.checkpoint_manager import CheckpointManager
from core.handoff.resume import ResumeManager
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter

def test_task_checkpoint_versioning():
    cm = CheckpointManager()
    pg = PostgresAdapter()
    
    task_id = f"task-ver-{uuid.uuid4().hex[:8]}"
    cm.create_task(task_id=task_id, goal="Demonstrate Checkpoint Versioning", created_by="agent-A")

    state_v1 = HandoverState(
        task_id=task_id,
        goal="Demonstrate Checkpoint Versioning",
        steps=[
            StepItem(id="step-1", status=StepStatus.DONE, state="Initiated scaffold", evidence=["Scaffold complete"])
        ],
        decisions=[DecisionItem(what="Decision 1", why="Reason 1", source="spec")],
        rejected=[],
        open_questions=[],
        written_by="agent-A"
    )

    cp1 = cm.save_checkpoint(task_id=task_id, state=state_v1)
    assert cp1["version"] == 1

    state_v2 = HandoverState(
        task_id=task_id,
        goal="Demonstrate Checkpoint Versioning",
        steps=[
            StepItem(id="step-1", status=StepStatus.DONE, state="Initiated scaffold", evidence=["Scaffold complete"]),
            StepItem(id="step-2", status=StepStatus.IN_PROGRESS, state="Writing tests", evidence=[])
        ],
        decisions=[DecisionItem(what="Decision 1", why="Reason 1", source="spec")],
        rejected=[RejectedOption(option="Option X", reason="Suboptimal")],
        open_questions=["Open question Y?"],
        written_by="agent-A"
    )

    cp2 = cm.save_checkpoint(task_id=task_id, state=state_v2)
    assert cp2["version"] == 2

    # Verify both versions exist in PostgreSQL
    rows = pg.execute_query(
        "SELECT version, written_by FROM checkpoints WHERE task_id = %s ORDER BY version ASC;",
        (task_id,)
    )
    assert len(rows) == 2
    assert rows[0]["version"] == 1
    assert rows[1]["version"] == 2

def test_resume_without_redis_and_without_transcript():
    cm = CheckpointManager()
    rm = ResumeManager()
    redis = RedisAdapter()
    pg = PostgresAdapter()

    task_id = f"task-resume-{uuid.uuid4().hex[:8]}"
    cm.create_task(task_id=task_id, goal="Build FastAPI Task API", created_by="agent-A")

    # Add a relevant bug to PostgreSQL to verify bug intelligence is included in resume
    bug_id = f"BUG-RESUME-{uuid.uuid4().hex[:4].upper()}"
    pg.execute_query(
        """
        INSERT INTO bugs (bug_id, title, symptom, status, severity, location, reported_by)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (bug_id) DO NOTHING;
        """,
        (bug_id, "FastAPI router mount order issue", "404 on sub-paths", "open", "medium",
         '{"files": ["api.py", "core/tasks.py"]}', "agent-A")
    )

    state = HandoverState(
        task_id=task_id,
        goal="Build FastAPI Task API",
        steps=[
            StepItem(id="step-1", status=StepStatus.DONE, state="Setup API models", evidence=["models/task.py"]),
            StepItem(id="step-2", status=StepStatus.IN_PROGRESS, state="Implement router in api.py", evidence=[])
        ],
        decisions=[
            DecisionItem(what="Use FastAPI APIRouter", why="Modular route registration", source="architecture")
        ],
        rejected=[
            RejectedOption(option="Monolithic app.py", reason="Poor maintainability")
        ],
        open_questions=["Should task deletion be soft or hard?"],
        written_by="agent-A"
    )
    cm.save_checkpoint(task_id=task_id, state=state)

    # Completely flush Redis to prove Redis is NOT required to recover durable task state
    redis.client.flushdb()

    # Agent B resumes fresh without Agent A's transcript
    resume_context = rm.resume_task(task_id=task_id, token_budget=800)
    
    assert resume_context["task_id"] == task_id
    assert resume_context["goal"] == "Build FastAPI Task API"
    assert resume_context["version"] == 1
    assert len(resume_context["steps"]) == 2
    assert resume_context["steps"][0]["status"] == "done"
    assert resume_context["steps"][1]["status"] == "in_progress"
    assert len(resume_context["decisions"]) == 1
    assert len(resume_context["rejected"]) == 1
    assert len(resume_context["open_questions"]) == 1
    assert "agent_a_transcript" not in resume_context  # Handover condition: no transcript

    # Verify bug history is included because api.py is referenced in the task
    assert "matching_bugs" in resume_context
    assert any(b["bug_id"] == bug_id for b in resume_context["matching_bugs"])

def test_invalid_checkpoint_rejected():
    cm = CheckpointManager()
    with pytest.raises(ValidationError):
        # Invalid status should raise ValidationError before database write
        HandoverState(
            task_id="invalid-task",
            goal="Test invalid",
            steps=[StepItem(id="1", status="unrecognized_status", state="Invalid")],
            decisions=[],
            rejected=[],
            open_questions=[],
            written_by="tester"
        )

