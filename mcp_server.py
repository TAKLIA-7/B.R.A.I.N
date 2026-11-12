from typing import Optional, Dict, Any, List
from fastmcp import FastMCP
from core.models.ingest import IngestRequest, SourceMetadata, SourceType
from core.models.checkpoint import HandoverState
from core.store.ingest import IngestionCoordinator
from core.retrieve.retriever import HybridRetriever
from core.handoff.checkpoint_manager import CheckpointManager
from core.handoff.resume import ResumeManager
from core.bugs.manager import BugManager
from core.bugs.projection import MarkdownProjectionGenerator
from core.forget.forget_manager import ForgetManager
from core.adapters.neo4j_adapter import Neo4jAdapter
from core.adapters.postgres import PostgresAdapter
from core.metrics.call_logger import log_mcp_call

mcp = FastMCP("Knowledge Brain")

coordinator = IngestionCoordinator()
retriever = HybridRetriever()
checkpoint_manager = CheckpointManager()
resume_manager = ResumeManager()
bug_manager = BugManager()
projection_generator = MarkdownProjectionGenerator()
forget_manager = ForgetManager()
neo4j_adapter = Neo4jAdapter()
pg_adapter = PostgresAdapter()

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
def task_checkpoint(task_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save durable task checkpoint state.
    Call this tool after every meaningful execution step to guarantee progress survives restarts.
    """
    validated_state = HandoverState.model_validate(state)
    saved = checkpoint_manager.save_checkpoint(task_id, validated_state)
    return {"status": "success", "checkpoint": saved}

@mcp.tool()
@log_mcp_call("task_resume")
def task_resume(task_id: str, token_budget: int = 1000) -> Dict[str, Any]:
    """
    Resume an existing task across restarts or model vendors.
    Call this at the beginning of every task to load goals, progress, decisions, and matching bug history.
    """
    return resume_manager.resume_task(task_id=task_id, token_budget=token_budget)

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

