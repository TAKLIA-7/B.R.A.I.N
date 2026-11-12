from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from core.models.ingest import IngestRequest, IngestResponse
from core.handoff.schemas import CheckpointState, ResumeResponse, HandoverState
from core.store.ingest import IngestionCoordinator
from core.retrieve.retriever import HybridRetriever
from core.handoff.checkpoint import CheckpointService
from core.handoff.resume import ResumeService
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter
from core.adapters.neo4j_adapter import Neo4jAdapter
from core.jev.engine import JEVDecisionEngine

app = FastAPI(
    title="Knowledge Brain API",
    description="Persistent Memory and Checkpoint Resumption Layer for AI Agents",
    version="0.2.0"
)

pg_adapter = PostgresAdapter()
redis_adapter = RedisAdapter()
neo4j_adapter = Neo4jAdapter()
jev_engine = JEVDecisionEngine(postgres_adapter=pg_adapter)
coordinator = IngestionCoordinator(postgres_adapter=pg_adapter, jev_engine=jev_engine)
retriever = HybridRetriever(postgres_adapter=pg_adapter, jev_engine=jev_engine)
checkpoint_service = CheckpointService(postgres_adapter=pg_adapter)
resume_service = ResumeService(postgres_adapter=pg_adapter)

# Backward-compatibility references
checkpoint_manager = checkpoint_service
resume_manager = resume_service

class SearchRequest(BaseModel):
    query: str
    token_budget: int = Field(default=500, ge=10, le=8000)
    task_id: Optional[str] = None

class CreateTaskRequest(BaseModel):
    task_id: str
    goal: str
    created_by: str
    status: str = "in_progress"

@app.get("/health")
def health():
    return {
        "status": "ok",
        "postgres": pg_adapter.check_health(),
        "redis": redis_adapter.ping(),
        "neo4j": neo4j_adapter.check_health(),
        "jev_enabled": jev_engine.enabled,
        "jev_model": jev_engine.client.model
    }

@app.post("/ingest", response_model=IngestResponse)
def ingest_content(request: IngestRequest):
    try:
        response = coordinator.process_ingestion(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@app.post("/search")
def search_memories(request: SearchRequest):
    try:
        response = retriever.search(
            query=request.query,
            token_budget=request.token_budget,
            task_id=request.task_id
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

# ================= Task & Checkpoint Endpoints =================

@app.post("/tasks")
def create_task_endpoint(request: CreateTaskRequest):
    """Initializes or creates a new task in PostgreSQL."""
    try:
        res = checkpoint_service.create_task(
            task_id=request.task_id,
            goal=request.goal,
            created_by=request.created_by,
            status=request.status
        )
        return {"status": "success", "task": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task creation failed: {str(e)}")

@app.post("/tasks/{task_id}/checkpoint")
def save_task_checkpoint(
    task_id: str,
    state: CheckpointState,
    expected_version: Optional[int] = Query(None)
):
    """
    Saves a persistent, versioned checkpoint for a task.
    Ensures strict version increment, updates task metadata, and caches in Redis.
    """
    try:
        if state.task_id != task_id:
            state.task_id = task_id
        res = checkpoint_service.save_checkpoint(state, expected_version=expected_version)
        return res
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Checkpoint save failed: {str(e)}")

@app.post("/tasks/checkpoint")
def legacy_task_checkpoint(state: HandoverState):
    """Legacy checkpoint endpoint for backward compatibility."""
    try:
        res = checkpoint_service.save_checkpoint(state)
        return {"status": "success", "checkpoint": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Checkpoint failed: {str(e)}")

@app.get("/tasks/{task_id}/checkpoints")
def get_task_checkpoints(task_id: str):
    """Returns the immutable version history of a task."""
    try:
        history = checkpoint_service.get_checkpoint_history(task_id)
        if not history:
            # Check if task exists
            status = checkpoint_service.get_task_status(task_id)
            if status.get("status") == "not_found":
                raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return {"task_id": task_id, "checkpoints": history}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch checkpoints: {str(e)}")

@app.get("/tasks/{task_id}/status")
def get_task_status(task_id: str):
    """Returns current task owner, status, and latest checkpoint version."""
    try:
        res = checkpoint_service.get_task_status(task_id)
        if res.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch task status: {str(e)}")

@app.get("/tasks/{task_id}/resume", response_model=ResumeResponse)
def resume_task_endpoint(
    task_id: str,
    requesting_agent: str = Query("agent"),
    token_budget: int = Query(4000, ge=50, le=32000)
):
    """
    Returns structured resumption context for an independent agent.
    Excludes conversational transcripts and prioritizes actionable state.
    """
    try:
        response = resume_service.resume_task(
            task_id=task_id,
            requesting_agent=requesting_agent,
            token_budget=token_budget
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resume failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
