import pytest
from fastapi.testclient import TestClient
from demo_api.main import app

client = TestClient(app)

def test_crud_lifecycle_task_api():
    # 1. Create a task
    create_resp = client.post("/tasks", json={
        "title": "Complete Knowledge Brain Handover Benchmark",
        "description": "Demonstrate cross-vendor portability between Agent A and Agent B",
        "priority": "high"
    })
    assert create_resp.status_code == 201
    task_data = create_resp.json()
    task_id = task_data["id"]
    assert task_data["title"] == "Complete Knowledge Brain Handover Benchmark"
    assert task_data["completed"] is False
    assert task_data["priority"] == "high"

    # 2. Get the task
    get_resp = client.get(f"/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == task_id

    # 3. Update the task
    update_resp = client.put(f"/tasks/{task_id}", json={
        "completed": True
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["completed"] is True

    # 4. List tasks
    list_resp = client.get("/tasks")
    assert list_resp.status_code == 200
    tasks = list_resp.json()
    assert any(t["id"] == task_id for t in tasks)

    # 5. Delete task
    del_resp = client.delete(f"/tasks/{task_id}")
    assert del_resp.status_code == 204

    # 6. Verify 404 after deletion
    get_deleted = client.get(f"/tasks/{task_id}")
    assert get_deleted.status_code == 404

def test_validation_error_handling():
    # Missing required title field
    bad_resp = client.post("/tasks", json={
        "description": "Missing title"
    })
    assert bad_resp.status_code == 422

