from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from core.models.ingest import IngestRequest, IngestResponse
from core.models.checkpoint import HandoverState
from core.store.ingest import IngestionCoordinator
from core.retrieve.retriever import HybridRetriever
from core.handoff.checkpoint_manager import CheckpointManager
from core.handoff.resume import ResumeManager
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter
from core.adapters.neo4j_adapter import Neo4jAdapter

app = FastAPI(
    title="Knowledge Brain API",
    description="Persistent Memory Layer for AI Agents",
    version="0.1.0"
)

coordinator = IngestionCoordinator()
retriever = HybridRetriever()
checkpoint_manager = CheckpointManager()
resume_manager = ResumeManager()
pg_adapter = PostgresAdapter()
redis_adapter = RedisAdapter()
neo4j_adapter = Neo4jAdapter()

class SearchRequest(BaseModel):
    query: str
    token_budget: int = Field(default=500, ge=10, le=8000)
    task_id: Optional[str] = None

@app.get("/health")
def health():
    return {
        "status": "ok",
        "postgres": pg_adapter.check_health(),
        "redis": redis_adapter.ping(),
        "neo4j": neo4j_adapter.check_health()
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

@app.post("/tasks/checkpoint")
def create_task_checkpoint(state: HandoverState):
    try:
        saved = checkpoint_manager.save_checkpoint(state.task_id, state)
        return {"status": "success", "checkpoint": saved}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Checkpoint failed: {str(e)}")

@app.get("/tasks/{task_id}/resume")
def resume_task_endpoint(task_id: str, token_budget: int = 1000):
    try:
        context = resume_manager.resume_task(task_id, token_budget=token_budget)
        if context.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=context["message"])
        return context
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resume failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
