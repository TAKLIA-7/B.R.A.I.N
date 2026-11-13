from typing import Optional, Dict, Any, List
from fastmcp import FastMCP
from core.models.ingest import IngestRequest, SourceMetadata, SourceType
from core.models.checkpoint import HandoverState, CheckpointState
from core.store.ingest import IngestionCoordinator
from core.retrieve.retriever import HybridRetriever
from core.handoff.checkpoint import CheckpointService
from core.handoff.resume import ResumeService
from core.bugs.manager import BugManager
from core.bugs.projection import MarkdownProjectionGenerator
from core.forget.forget_manager import ForgetManager
from core.evolution.manager import RequirementManager
from core.evolution.schemas import (
    RequirementCreateRequest,
    RequirementProposalRequest,
    RequirementApprovalRequest
)
from core.project_knowledge.manager import ProjectKnowledgeManager
from core.project_knowledge.schemas import ProjectCreateRequest
from core.adapters.neo4j_adapter import Neo4jAdapter
from core.adapters.postgres import PostgresAdapter
from core.metrics.call_logger import log_mcp_call
from core.jev.engine import JEVDecisionEngine

mcp = FastMCP("Knowledge Brain")

pg_adapter = PostgresAdapter()
jev_engine = JEVDecisionEngine(postgres_adapter=pg_adapter)
coordinator = IngestionCoordinator(postgres_adapter=pg_adapter, jev_engine=jev_engine)
retriever = HybridRetriever(postgres_adapter=pg_adapter, jev_engine=jev_engine)
checkpoint_manager = CheckpointService(postgres_adapter=pg_adapter)
resume_manager = ResumeService(postgres_adapter=pg_adapter)
bug_manager = BugManager()
projection_generator = MarkdownProjectionGenerator()
forget_manager = ForgetManager()
neo4j_adapter = Neo4jAdapter()
req_manager = RequirementManager(postgres_adapter=pg_adapter)
project_manager = ProjectKnowledgeManager(postgres_adapter=pg_adapter)

@mcp.tool()
@log_mcp_call("memory_search")
def memory_search(query: str, token_budget: int = 500, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Search Knowledge Brain for relevant memories, facts, preferences, decisions, and bug history.
    Enforces the requested token budget and abstains if evidence is weak.
    Call this tool before assuming relevant context is unknown.
    """
    return retriever.search(query=query, token_budget=token_budget, task_id=task_id)

@mcp.tool()
@log_mcp_call("memory_store")
def memory_store(content: str, type: str = "fact", source_actor: str = "agent") -> Dict[str, Any]:
    """
    Ingest and store durable knowledge (facts, decisions, procedures, preferences).
    Attributes provenance and applies deterministic storage routing.
    """
    source_type = SourceType.AGENT if "agent" in source_actor.lower() else SourceType.USER
    req = IngestRequest(
        source=SourceMetadata(type=source_type, actor=source_actor, trust_level=0.8),
        content=content
    )
    res = coordinator.process_ingestion(req)
    return res.model_dump()

@mcp.tool()
@log_mcp_call("memory_update")
def memory_update(id: str, change: str, reason: str, agent: str = "agent") -> Dict[str, Any]:
    """
    Update an existing memory with superseding information while preserving append-only history.
    """
    # Fetch existing memory
    rows = pg_adapter.execute_query("SELECT * FROM memories WHERE id = %s;", (id,))
    if not rows:
        return {"status": "error", "message": f"Memory {id} not found"}

    old_mem = rows[0]
    # Mark old memory superseded
    pg_adapter.execute_query("UPDATE memories SET status = 'superseded', valid_until = NOW() WHERE id = %s;", (id,))

    # Ingest updated memory referencing superseded ID
    import uuid
    new_id = str(uuid.uuid4())
    pg_adapter.execute_query(
        """
        INSERT INTO memories (id, type, text, status, epistemic_state, source_id, supersedes_id, created_at)
        VALUES (%s, %s, %s, 'active', 'asserted', %s, %s, NOW())
        RETURNING id, type, text, status;
        """,
        (new_id, old_mem["type"], change, old_mem["source_id"], id)
    )
    return {"status": "success", "superseded_id": id, "new_id": new_id, "reason": reason}

@mcp.tool()
@log_mcp_call("memory_check_conflict")
def memory_check_conflict(memory_id: str, new_claim: str, trust_level: float = 0.8) -> Dict[str, Any]:
    """
    Consult JEV to detect potential conflicts between a stored memory and a new claim.
    Returns resolution (supersede, dispute, coexist, reject) and assigned epistemic state.
    """
    rows = pg_adapter.execute_query("SELECT id, text, trust_score, epistemic_state FROM memories WHERE id = %s;", (memory_id,))
    if not rows:
        return {"status": "error", "message": f"Memory {memory_id} not found"}
    decision, audit = jev_engine.decide_conflict(rows[0], new_claim, trust_level)
    return {
        "status": "success",
        "decision": decision.model_dump(),
        "audit_id": audit.get("decision_id")
    }

@mcp.tool()
@log_mcp_call("memory_forget")
def memory_forget(scope: str, agent: str = "agent") -> Dict[str, Any]:
    """
    Perform verified forgetting for a memory ID, actor, or text scope.
    Removes records from PostgreSQL, pgvector, Redis, and Neo4j,
    and returns a verified deletion audit receipt.
    """
    return forget_manager.forget(scope=scope)

@mcp.tool()
@log_mcp_call("task_checkpoint")
def task_checkpoint(
    task_id: str,
    goal: Optional[str] = None,
    steps: Optional[List[Dict[str, Any]]] = None,
    decisions: Optional[List[Dict[str, Any]]] = None,
    rejected: Optional[List[Dict[str, Any]]] = None,
    open_questions: Optional[List[str]] = None,
    written_by: str = "agent",
    project_files: Optional[List[str]] = None,
    test_results: Optional[List[str]] = None,
    git_commit: Optional[str] = None,
    git_branch: Optional[str] = None,
    state: Optional[Dict[str, Any]] = None,
    expected_version: Optional[int] = None
) -> Dict[str, Any]:
    """
    Save durable task checkpoint state.
    Call this tool after every meaningful execution step to guarantee progress survives restarts.
    """
    if state is not None:
        raw_state = dict(state)
        if "task_id" not in raw_state:
            raw_state["task_id"] = task_id
        if "written_by" not in raw_state and written_by:
            raw_state["written_by"] = written_by
    else:
        raw_state = {
            "task_id": task_id,
            "goal": goal or "",
            "steps": steps or [],
            "decisions": decisions or [],
            "rejected": rejected or [],
            "open_questions": open_questions or [],
            "written_by": written_by,
            "project_files": project_files or [],
            "test_results": test_results or [],
            "git_commit": git_commit,
            "git_branch": git_branch
        }
    validated_state = CheckpointState.model_validate(raw_state)
    res = checkpoint_manager.save_checkpoint(state=validated_state, expected_version=expected_version)
    out = dict(res)
    out["status"] = "success"
    out["version"] = res["checkpoint_version"]
    out["checkpoint"] = dict(res)
    return out

@mcp.tool()
@log_mcp_call("task_resume")
def task_resume(
    task_id: str,
    requesting_agent: str = "agent",
    token_budget: int = 4000
) -> Dict[str, Any]:
    """
    Resume an existing task across restarts or model vendors.
    Call this at the beginning of every task to load goals, progress, decisions, and matching bug history.
    """
    res = resume_manager.resume_task(
        task_id=task_id,
        requesting_agent=requesting_agent,
        token_budget=token_budget
    )
    return res.model_dump()

@mcp.tool()
@log_mcp_call("bug_report")
def bug_report(
    bug_id: str,
    title: str,
    symptom: str,
    root_cause: Optional[str] = None,
    severity: str = "medium",
    location: Optional[Dict[str, Any]] = None,
    signature: Optional[str] = None,
    reported_by: str = "agent"
) -> Dict[str, Any]:
    """Report a new defect with symptoms, location, and severity."""
    res = bug_manager.report_bug(
        bug_id=bug_id, title=title, symptom=symptom, root_cause=root_cause,
        severity=severity, location=location, signature=signature, reported_by=reported_by
    )
    try:
        projection_generator.sync_all_projections()
    except Exception:
        pass
    return res

@mcp.tool()
@log_mcp_call("bug_log_attempt")
def bug_log_attempt(
    bug_id: str,
    agent: str,
    hypothesis: str,
    action: str,
    outcome: str,
    evidence: Optional[Dict[str, Any]] = None,
    learned: Optional[str] = None
) -> Dict[str, Any]:
    """Log an investigation attempt, including failed and partial attempts."""
    res = bug_manager.log_attempt(
        bug_id=bug_id, agent=agent, hypothesis=hypothesis, action=action,
        outcome=outcome, evidence=evidence, learned=learned
    )
    try:
        projection_generator.sync_all_projections()
    except Exception:
        pass
    return res

@mcp.tool()
@log_mcp_call("bug_record_fix")
def bug_record_fix(
    fix_id: str,
    bug_id: str,
    commit: Optional[str],
    files_changed: List[str],
    summary: str,
    verification: Dict[str, Any],
    fixed_by: str,
    supersedes_fix: Optional[str] = None
) -> Dict[str, Any]:
    """Record a verified fix with empirical test verification results."""
    res = bug_manager.record_fix(
        fix_id=fix_id, bug_id=bug_id, commit=commit, files_changed=files_changed,
        summary=summary, verification=verification, fixed_by=fixed_by, supersedes_fix=supersedes_fix
    )
    try:
        projection_generator.sync_all_projections()
    except Exception:
        pass
    return res

@mcp.tool()
@log_mcp_call("bug_search")
def bug_search(query: str) -> List[Dict[str, Any]]:
    """Search structured bug records by file, symbol, error message, or symptom."""
    return bug_manager.search_bugs(query)

@mcp.tool()
@log_mcp_call("bug_history")
def bug_history(bug_id: str) -> Dict[str, Any]:
    """Retrieve full audit history for a bug, including attempts, fixes, and events."""
    return bug_manager.get_bug_history(bug_id)

@mcp.tool()
@log_mcp_call("knowledge_graph_search")
def knowledge_graph_search(query: str, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search entity relationships and dependencies in the Neo4j knowledge graph."""
    terms = [t.lower() for t in query.split() if len(t) > 2][:4]
    if not terms:
        return []
    cypher = """
        MATCH (s:Entity)-[r]->(o:Entity)
        WHERE any(t IN $terms WHERE toLower(s.name) CONTAINS t OR toLower(o.name) CONTAINS t)
        RETURN s.name AS subject, type(r) AS predicate, o.name AS object, 
               r.epistemic_state AS state, r.canonical_memory_id AS memory_id
        LIMIT 15;
    """
    return neo4j_adapter.execute_cypher(cypher, {"terms": terms})

# ================= Project Knowledge MCP Tools =================

@mcp.tool()
@log_mcp_call("project_register")
def project_register(
    id: str,
    name: str,
    description: Optional[str] = None,
    repository_url: Optional[str] = None,
    root_path: Optional[str] = None
) -> Dict[str, Any]:
    """Registers a project and scaffolds its human-readable Markdown knowledge base."""
    req = ProjectCreateRequest(id=id, name=name, description=description, repository_url=repository_url, root_path=root_path)
    item = project_manager.register_project(req)
    return item.model_dump()

@mcp.tool()
@log_mcp_call("project_get")
def project_get(project_id: str) -> Dict[str, Any]:
    """Retrieves metadata for a registered project."""
    p = project_manager.get_project(project_id)
    return p.model_dump() if p else {"status": "not_found", "message": f"Project {project_id} not found"}

@mcp.tool()
@log_mcp_call("project_context")
def project_context(project_id: str, task: Optional[str] = None, token_budget: int = 4000) -> Dict[str, Any]:
    """
    Retrieves task-aware project context from overview, tech stack, architecture,
    and approved requirements within the specified token budget.
    """
    res = project_manager.get_project_context(project_id=project_id, task=task, token_budget=token_budget)
    return res.model_dump()

@mcp.tool()
@log_mcp_call("project_documents_list")
def project_documents_list(project_id: str) -> List[Dict[str, Any]]:
    """Lists registered project documents and their synchronization state."""
    docs = project_manager.list_documents(project_id)
    return [d.model_dump() for d in docs]

@mcp.tool()
@log_mcp_call("project_document_get")
def project_document_get(project_id: str, relative_path: str) -> Dict[str, Any]:
    """Retrieves document content from disk and its metadata from PostgreSQL."""
    doc = project_manager.get_document(project_id, relative_path)
    return doc if doc else {"status": "not_found", "message": f"Document {relative_path} not found"}

@mcp.tool()
@log_mcp_call("project_document_sync")
def project_document_sync(
    project_id: str,
    relative_path: str,
    content: str,
    document_type: str = "custom",
    force: bool = False
) -> Dict[str, Any]:
    """Synchronizes a project Markdown document to disk and updates PostgreSQL."""
    success, status = project_manager.sync.sync_document(project_id, relative_path, document_type, content, force=force)
    return {"success": success, "status": status, "relative_path": relative_path}

@mcp.tool()
@log_mcp_call("project_document_validate")
def project_document_validate(project_id: str, relative_path: str) -> Dict[str, Any]:
    """Validates document synchronization state against disk content hash."""
    doc = project_manager.get_document(project_id, relative_path)
    if not doc:
        return {"status": "not_found", "message": f"Document {relative_path} not registered"}
    return {"status": doc["status"], "version": doc["version"], "content_hash": doc["content_hash"]}

# ================= Requirement Evolution MCP Tools =================

@mcp.tool()
@log_mcp_call("requirement_propose")
def requirement_propose(
    req_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    proposed_description: Optional[str] = None,
    project_id: Optional[str] = None,
    module: str = "general",
    category: str = "functional",
    priority: str = "medium",
    acceptance_criteria: Optional[List[str]] = None,
    reason: Optional[str] = None,
    proposed_by: str = "agent"
) -> Dict[str, Any]:
    """
    Creates a new requirement or proposes an upgrade to an existing requirement.
    Preserves historical versions and does not activate unapproved changes.
    """
    existing = req_manager.get_requirement(req_id)
    if not existing:
        create_req = RequirementCreateRequest(
            req_id=req_id,
            title=title or req_id,
            description=description or proposed_description or "",
            project_id=project_id,
            module=module,
            category=category,
            priority=priority,
            acceptance_criteria=acceptance_criteria or [],
            created_by=proposed_by,
            initial_status="approved" if not proposed_description else "proposed"
        )
        item = req_manager.create_requirement(create_req)
        if project_id:
            try:
                hist = req_manager.get_requirement_history(req_id)
                project_manager.sync_requirement_doc(project_id, req_id, item.model_dump(), [h.model_dump() for h in hist])
            except Exception:
                pass
        return {"success": True, "action": "created", "requirement": item.model_dump()}
    else:
        proposal = RequirementProposalRequest(
            req_id=req_id,
            proposed_description=proposed_description or description or "",
            acceptance_criteria=acceptance_criteria or [],
            reason=reason or "Specification update",
            proposed_by=proposed_by
        )
        res = req_manager.propose_version(proposal)
        return {"success": True, "action": "proposed", **res}

@mcp.tool()
@log_mcp_call("requirement_approve")
def requirement_approve(
    req_id: str,
    target_version: int,
    decision: str = "approved",
    approver: str = "lead_architect",
    rationale: Optional[str] = None
) -> Dict[str, Any]:
    """Approves or rejects a proposed requirement version. Automatically flags affected tasks as stale."""
    app_req = RequirementApprovalRequest(
        req_id=req_id,
        target_version=target_version,
        decision=decision,
        approver=approver,
        rationale=rationale
    )
    res = req_manager.approve_version(app_req)
    req_item = req_manager.get_requirement(req_id)
    if req_item and req_item.project_id:
        try:
            hist = req_manager.get_requirement_history(req_id)
            project_manager.sync_requirement_doc(req_item.project_id, req_id, req_item.model_dump(), [h.model_dump() for h in hist])
        except Exception:
            pass
    return res

@mcp.tool()
@log_mcp_call("requirement_get")
def requirement_get(req_id: str) -> Dict[str, Any]:
    """Retrieves current approved requirement and version metadata."""
    req = req_manager.get_requirement(req_id)
    return req.model_dump() if req else {"status": "not_found", "message": f"Requirement {req_id} not found"}

@mcp.tool()
@log_mcp_call("requirement_history")
def requirement_history(req_id: str) -> List[Dict[str, Any]]:
    """Retrieves full immutable version history for a requirement."""
    hist = req_manager.get_requirement_history(req_id)
    return [h.model_dump() for h in hist]

@mcp.tool()
@log_mcp_call("requirement_impact")
def requirement_impact(req_id: str, version: Optional[int] = None) -> Dict[str, Any]:
    """Retrieves blast-radius impact analysis for a requirement version."""
    req = req_manager.get_requirement(req_id)
    if not req:
        return {"status": "not_found", "message": f"Requirement {req_id} not found"}
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
    return req_manager.compute_and_store_impact(req_id, v, req.module, req.current_description or "").model_dump()

@mcp.tool()
@log_mcp_call("requirement_check_staleness")
def requirement_check_staleness(task_id: str) -> Dict[str, Any]:
    """Checks whether an agent's task is stale due to upstream requirement upgrades."""
    rep = req_manager.check_task_staleness(task_id)
    return rep.model_dump()

@mcp.prompt()
def resume_task(task_id: str) -> str:
    """MCP prompt guiding an agent resuming a task using Knowledge Brain memory."""
    return f"""
You are continuing execution of task '{task_id}'.
Follow these instructions:
1. Call `task_resume(task_id='{task_id}')` to obtain the latest checkpoint, decisions, open questions, and matching bug history.
2. Review completed steps and continue with in-progress or pending steps.
3. Call `task_checkpoint(task_id='{task_id}', state=...)` after completing every meaningful step.
4. Record any defects found using `bug_report` and failed debugging attempts using `bug_log_attempt`.
5. Verify fixes with automated tests before calling `bug_record_fix`.
"""

if __name__ == "__main__":
    mcp.run()

