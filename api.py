from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from core.models.ingest import IngestRequest, IngestResponse
from core.handoff.schemas import CheckpointState, ResumeResponse, HandoverState
from core.evolution.manager import RequirementManager
from core.evolution.schemas import (
    RequirementCreateRequest,
    RequirementProposalRequest,
    RequirementApprovalRequest,
    RequirementItem,
    RequirementImpact,
    TaskStalenessReport
)
from core.project_knowledge.manager import ProjectKnowledgeManager
from core.project_knowledge.schemas import (
    ProjectCreateRequest,
    ProjectItem,
    ProjectDocumentItem,
    ProjectContextResponse
)
from core.store.ingest import IngestionCoordinator
from core.retrieve.retriever import HybridRetriever
from core.handoff.checkpoint import CheckpointService
from core.handoff.resume import ResumeService
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter
from core.adapters.neo4j_adapter import Neo4jAdapter
from core.jev.engine import JEVDecisionEngine
from core.agent_monitor import CheckpointScheduler, AgentUsageMetrics
from core.conflict.manager import ConflictManager
from core.conflict.schemas import HumanApprovalAction, ClarificationRequest, ConflictApprovalItem

app = FastAPI(
    title="Knowledge Brain API",
    description="Persistent Memory, Project Knowledge, and Dynamic Evolution Layer for AI Agents",
    version="0.3.0"
)

pg_adapter = PostgresAdapter()
redis_adapter = RedisAdapter()
neo4j_adapter = Neo4jAdapter()
jev_engine = JEVDecisionEngine(postgres_adapter=pg_adapter)
coordinator = IngestionCoordinator(postgres_adapter=pg_adapter, jev_engine=jev_engine)
retriever = HybridRetriever(postgres_adapter=pg_adapter, jev_engine=jev_engine)
checkpoint_service = CheckpointService(postgres_adapter=pg_adapter)
resume_service = ResumeService(postgres_adapter=pg_adapter)
req_manager = RequirementManager(postgres_adapter=pg_adapter)
project_manager = ProjectKnowledgeManager(postgres_adapter=pg_adapter)
checkpoint_scheduler = CheckpointScheduler(postgres_adapter=pg_adapter, checkpoint_service=checkpoint_service)
conflict_manager = ConflictManager(postgres_adapter=pg_adapter, jev_engine=jev_engine)

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

# ================= Project Knowledge Endpoints =================

@app.post("/projects", response_model=ProjectItem)
def register_project_endpoint(request: ProjectCreateRequest):
    """Registers a project and scaffolds its human-readable Markdown knowledge base."""
    try:
        return project_manager.register_project(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Project registration failed: {str(e)}")

@app.get("/projects/{project_id}", response_model=ProjectItem)
def get_project_endpoint(project_id: str):
    """Retrieves project metadata."""
    p = project_manager.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return p

@app.get("/projects/{project_id}/documents", response_model=List[ProjectDocumentItem])
def list_project_documents_endpoint(project_id: str):
    """Lists registered project documents and their synchronization state."""
    return project_manager.list_documents(project_id)

@app.get("/projects/{project_id}/context", response_model=ProjectContextResponse)
def get_project_context_endpoint(
    project_id: str,
    task: Optional[str] = Query(None),
    token_budget: int = Query(4000, ge=10, le=32000)
):
    """Task-aware project context retrieval."""
    try:
        return project_manager.get_project_context(project_id=project_id, task=task, token_budget=token_budget)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch context: {str(e)}")

# ================= Requirement Evolution Endpoints =================

@app.post("/requirements/create", response_model=RequirementItem)
def create_requirement_endpoint(request: RequirementCreateRequest):
    """Creates a new canonical requirement and initial version."""
    try:
        return req_manager.create_requirement(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Requirement creation failed: {str(e)}")

@app.post("/requirements/propose")
def propose_requirement_endpoint(request: RequirementProposalRequest):
    """Proposes an upgrade version for a requirement without activating it."""
    try:
        return req_manager.propose_version(request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Requirement proposal failed: {str(e)}")

@app.post("/requirements/{req_id}/approve")
def approve_requirement_endpoint(req_id: str, request: RequirementApprovalRequest):
    """Approves or rejects a proposed requirement version and updates task staleness."""
    try:
        if request.req_id != req_id:
            request.req_id = req_id
        return req_manager.approve_version(request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Requirement approval failed: {str(e)}")

@app.get("/requirements/{req_id}", response_model=RequirementItem)
def get_requirement_endpoint(req_id: str):
    """Retrieves current approved requirement and version metadata."""
    req = req_manager.get_requirement(req_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Requirement '{req_id}' not found")
    return req

@app.get("/requirements/{req_id}/history")
def get_requirement_history_endpoint(req_id: str):
    """Retrieves full immutable version history for a requirement."""
    return req_manager.get_requirement_history(req_id)

@app.get("/requirements/{req_id}/impact")
def get_requirement_impact_endpoint(req_id: str, version: Optional[int] = Query(None)):
    """Retrieves blast-radius impact analysis for a requirement version."""
    req = req_manager.get_requirement(req_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Requirement '{req_id}' not found")
    v = version or req.current_version
    rows = pg_adapter.execute_query(
        "SELECT * FROM requirement_impacts WHERE req_id = %s AND version = %s ORDER BY created_at DESC LIMIT 1;",
        (req_id, v)
    )
    if rows:
        r = rows[0]
        return {
            "req_id": r["req_id"],
            "version": r["version"],
            "affected_modules": r["affected_modules"],
            "affected_files": r["affected_files"],
            "affected_endpoints": r["affected_endpoints"],
            "affected_entities": r["affected_entities"],
            "affected_tasks": r["affected_tasks"],
            "affected_tests": r["affected_tests"]
        }
    return req_manager.compute_and_store_impact(req_id, v, req.module, req.current_description or "")

@app.get("/tasks/{task_id}/staleness", response_model=TaskStalenessReport)
def get_task_staleness_endpoint(task_id: str):
    """Checks whether a task is stale due to upstream requirement upgrades."""
    return req_manager.check_task_staleness(task_id)

@app.post("/tasks/{task_id}/associate_requirement")
def associate_task_requirement_endpoint(task_id: str, req_id: str = Query(...), version: Optional[int] = Query(None)):
    """Associates an agent task with a target requirement version."""
    try:
        req_manager.associate_task_with_requirement(task_id, req_id, version)
        return {"status": "success", "task_id": task_id, "req_id": req_id, "version": version}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to associate task with requirement: {str(e)}")

# ================= Proactive Agent Monitor Endpoints =================

class AgentUsagePayload(BaseModel):
    agent_name: str
    tokens_consumed: Optional[int] = None
    context_window_capacity: Optional[int] = None
    usage_percentage: Optional[float] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    model_name: Optional[str] = None
    project_id: Optional[str] = None
    auto_checkpoint: bool = True
    account_quota_info: Optional[Dict[str, Any]] = None

class ProactiveCheckpointPayload(BaseModel):
    task_id: str
    project_id: Optional[str] = None
    trigger_reason: str = "manual_assisted"
    agent_name: str = "agent"
    session_id: Optional[str] = None
    state: Optional[CheckpointState] = None

@app.post("/agent/usage")
def report_agent_usage(payload: AgentUsagePayload):
    """
    Ingests AI agent usage telemetry, evaluates against context threshold policies (70%, 80%, 90%, 95%),
    and automatically triggers proactive checkpoint updates when thresholds are crossed.
    """
    try:
        metrics = AgentUsageMetrics(
            agent_name=payload.agent_name,
            tokens_consumed=payload.tokens_consumed,
            context_window_capacity=payload.context_window_capacity,
            usage_percentage=payload.usage_percentage,
            session_id=payload.session_id,
            task_id=payload.task_id,
            model_name=payload.model_name,
            account_quota_info=payload.account_quota_info,
            source="rest_api"
        )
        if not payload.auto_checkpoint:
            return {
                "status": "recorded",
                "usage_percentage": metrics.get_effective_usage_percentage()
            }
        return checkpoint_scheduler.process_usage_telemetry(metrics=metrics, project_id=payload.project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process agent usage: {str(e)}")

@app.post("/agent/checkpoint/proactive")
def trigger_proactive_checkpoint(payload: ProactiveCheckpointPayload):
    """Manually or programmatically triggers an immediate checkpoint update for an active task and project."""
    try:
        return checkpoint_scheduler.execute_checkpoint(
            task_id=payload.task_id,
            state=payload.state,
            project_id=payload.project_id,
            trigger_reason=payload.trigger_reason,
            session_id=payload.session_id,
            agent_name=payload.agent_name
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proactive checkpoint failed: {str(e)}")

@app.get("/agent/checkpoint/triggers/{task_id}")
def get_checkpoint_triggers(task_id: str):
    """Retrieves the audit log of checkpoint triggers and threshold events for a task."""
    try:
        sql = """
            SELECT id, task_id, project_id, agent_name, session_id,
                   trigger_reason, context_percentage, tokens_consumed, tokens_capacity,
                   checkpoint_version, idempotency_key, status, details, created_at
            FROM checkpoint_triggers
            WHERE task_id = %s
            ORDER BY created_at DESC;
        """
        rows = pg_adapter.execute_query(sql, (task_id,))
        return {"task_id": task_id, "triggers": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch checkpoint triggers: {str(e)}")

# ================= Human-in-the-Loop Conflict Resolution Endpoints =================

class CheckConflictRequest(BaseModel):
    claim: str
    project_id: Optional[str] = None
    source_actor: str = "agent"
    trust_level: float = 0.5

@app.get("/conflicts/pending")
def list_pending_conflicts(project_id: Optional[str] = Query(None)):
    """Lists all pending knowledge conflicts awaiting human arbitration."""
    try:
        items = conflict_manager.list_pending_approvals(project_id=project_id)
        return {"pending_conflicts": [i.model_dump() for i in items]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list pending conflicts: {str(e)}")

@app.get("/conflicts/{conflict_id}")
def get_conflict_details(conflict_id: str):
    """Retrieves full details, rule IDs, existing snapshot, and evidence for a conflict."""
    item = conflict_manager.get_conflict(conflict_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Conflict '{conflict_id}' not found")
    return item.model_dump()

@app.post("/conflicts/{conflict_id}/approve")
def approve_conflict_endpoint(conflict_id: str, payload: HumanApprovalAction):
    """
    Approves a knowledge conflict.
    Only authorized humans may approve. AI agents are strictly forbidden from approving their own conflicts.
    """
    try:
        res = conflict_manager.approve_conflict(
            conflict_id=conflict_id,
            approver=payload.approver,
            rationale=payload.rationale,
            selected_resolution=payload.selected_resolution,
            is_human=payload.is_human
        )
        return res
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval execution failed: {str(e)}")

@app.post("/conflicts/{conflict_id}/reject")
def reject_conflict_endpoint(conflict_id: str, payload: HumanApprovalAction):
    """
    Rejects a proposed conflicting change.
    Existing canonical knowledge remains strictly unchanged and no derived stores are updated.
    """
    try:
        res = conflict_manager.reject_conflict(
            conflict_id=conflict_id,
            approver=payload.approver,
            rationale=payload.rationale or "Rejected by human",
            is_human=payload.is_human
        )
        return res
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rejection failed: {str(e)}")

@app.post("/conflicts/{conflict_id}/clarify")
def clarify_conflict_endpoint(conflict_id: str, payload: ClarificationRequest):
    """Submits clarification or additional evidence for a pending conflict."""
    try:
        item = conflict_manager.submit_clarification(
            conflict_id=conflict_id,
            author=payload.author,
            clarification_notes=payload.clarification_notes,
            updated_claim=payload.updated_claim,
            additional_evidence=payload.additional_evidence
        )
        return item.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clarification submission failed: {str(e)}")

@app.post("/conflicts/check")
def check_conflict_endpoint(payload: CheckConflictRequest):
    """Checks whether a claim triggers a conflict requiring human approval."""
    try:
        is_conf, item = conflict_manager.check_and_register_conflict(
            incoming_claim=payload.claim,
            source_actor=payload.source_actor,
            trust_level=payload.trust_level,
            project_id=payload.project_id
        )
        return {
            "conflict_detected": is_conf,
            "requires_human_approval": is_conf,
            "conflict": item.model_dump() if item else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conflict check failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
