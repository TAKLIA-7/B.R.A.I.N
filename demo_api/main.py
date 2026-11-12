import uuid
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from demo_api.models import TaskCreate, TaskUpdate, TaskResponse

app = FastAPI(title="Task Management REST API", version="1.0.0")

# In-memory storage for the checkable demonstration task
TASKS_DB: Dict[str, TaskResponse] = {}

@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate):
    task_id = str(uuid.uuid4())
    task = TaskResponse(
        id=task_id,
        title=payload.title,
        description=payload.description,
        completed=False,
        priority=payload.priority
    )
    TASKS_DB[task_id] = task
    return task

@app.get("/tasks", response_model=List[TaskResponse])
def list_tasks():
    return list(TASKS_DB.values())

@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    if task_id not in TASKS_DB:
        raise HTTPException(status_code=404, detail="Task not found")
    return TASKS_DB[task_id]

@app.put("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: str, payload: TaskUpdate):
    if task_id not in TASKS_DB:
        raise HTTPException(status_code=404, detail="Task not found")
    task = TASKS_DB[task_id]
    update_data = payload.model_dump(exclude_unset=True)
    updated = task.model_copy(update=update_data)
    TASKS_DB[task_id] = updated
    return updated

@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str):
    if task_id not in TASKS_DB:
        raise HTTPException(status_code=404, detail="Task not found")
    del TASKS_DB[task_id]
    return None

