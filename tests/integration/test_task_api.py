import uuid
import pytest
from fastapi.testclient import TestClient
from api import app
from core.adapters.postgres import PostgresAdapter

client = TestClient(app)

def test_task_rest_api_lifecycle():
    task_id = f"REST-TASK-{uuid.uuid4().hex[:6]}"

    # 1. POST /tasks
    create_resp = client.post("/tasks", json={
        "task_id": task_id,
        "goal": "Build REST Authentication",
        "created_by": "Agent A"
    })
    assert create_resp.status_code == 200
    create_data = create_resp.json()
    assert create_data["status"] == "success"
    assert create_data["task"]["id"] == task_id
    assert create_data["task"]["goal"] == "Build REST Authentication"
    assert create_data["task"]["current_owner"] == "Agent A"

    # 2. POST /tasks/{task_id}/checkpoint (Version 1)
    cp_resp1 = client.post(f"/tasks/{task_id}/checkpoint", json={
        "task_id": task_id,
        "goal": "Build REST Authentication",
        "steps": [
            {"id": "step-1", "status": "done", "state": "Scaffolded endpoints", "evidence": ["api.py"]}
        ],
        "decisions": [
            {"what": "Use FastAPI", "why": "High performance", "source": "tech_spec"}
        ],
        "rejected": [
            {"option": "Flask", "reason": "No native async support"}
        ],
        "open_questions": ["JWT vs Session cookies?"],
        "written_by": "Agent A",
        "project_files": ["api.py"]
    })
    assert cp_resp1.status_code == 200
    cp_data1 = cp_resp1.json()
    assert cp_data1["success"] is True
    assert cp_data1["task_id"] == task_id
    assert cp_data1["checkpoint_version"] == 1
    assert cp_data1["written_by"] == "Agent A"

    # 3. POST /tasks/{task_id}/checkpoint (Version 2)
    cp_resp2 = client.post(f"/tasks/{task_id}/checkpoint", json={
        "task_id": task_id,
        "goal": "Build REST Authentication",
        "steps": [
            {"id": "step-1", "status": "done", "state": "Scaffolded endpoints", "evidence": ["api.py"]},
            {"id": "step-2", "status": "in_progress", "state": "Implementing JWT handling", "evidence": []}
        ],
        "decisions": [
            {"what": "Use FastAPI", "why": "High performance", "source": "tech_spec"},
            {"what": "JWT with Ed25519", "why": "Security", "source": "sec_audit"}
        ],
        "rejected": [
            {"option": "Flask", "reason": "No native async support"}
        ],
        "open_questions": [],
        "written_by": "Agent A",
        "project_files": ["api.py", "auth.py"]
    })
    assert cp_resp2.status_code == 200
    cp_data2 = cp_resp2.json()
    assert cp_data2["checkpoint_version"] == 2

    # 4. GET /tasks/{task_id}/status
    status_resp = client.get(f"/tasks/{task_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["task_id"] == task_id
    assert status_data["current_owner"] == "Agent A"
    assert status_data["latest_version"] == 2

    # 5. GET /tasks/{task_id}/checkpoints
    history_resp = client.get(f"/tasks/{task_id}/checkpoints")
    assert history_resp.status_code == 200
    history_data = history_resp.json()
    assert history_data["task_id"] == task_id
    assert len(history_data["checkpoints"]) == 2
    assert history_data["checkpoints"][0]["version"] == 1
    assert history_data["checkpoints"][1]["version"] == 2

    # 6. GET /tasks/{task_id}/resume (Agent B resumes)
    resume_resp = client.get(f"/tasks/{task_id}/resume?requesting_agent=Agent%20B&token_budget=2000")
    assert resume_resp.status_code == 200
    resume_data = resume_resp.json()
    assert resume_data["task_id"] == task_id
    assert resume_data["checkpoint_version"] == 2
    assert resume_data["previous_agent"] == "Agent A"
    assert resume_data["requesting_agent"] == "Agent B"
    assert len(resume_data["completed_steps"]) == 1
    assert len(resume_data["pending_steps"]) == 1
    assert "handover_context" in resume_data

    # 7. Check that owner updated to Agent B
    status_resp_after = client.get(f"/tasks/{task_id}/status")
    assert status_resp_after.status_code == 200
    assert status_resp_after.json()["current_owner"] == "Agent B"

