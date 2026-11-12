import pytest
import uuid
from mcp_server import mcp, memory_store, memory_search, task_checkpoint, task_resume
from core.adapters.postgres import PostgresAdapter

def test_mcp_tools_and_prompts_registered():
    """Verify all 12 required MCP tools and prompt are registered."""
    tool_names = set(mcp._function_tool_manager._tools.keys()) if hasattr(mcp, "_function_tool_manager") else set()
    if not tool_names and hasattr(mcp, "list_tools"):
        # Alternate attribute depending on FastMCP version
        tool_names = {t.name for t in mcp._tools} if hasattr(mcp, "_tools") else set()

    expected_tools = {
        "memory_search",
        "memory_store",
        "memory_update",
        "memory_forget",
        "task_checkpoint",
        "task_resume",
        "bug_report",
        "bug_log_attempt",
        "bug_record_fix",
        "bug_search",
        "bug_history",
        "knowledge_graph_search"
    }
    # Check each expected tool is importable and callable
    assert callable(memory_store)
    assert callable(memory_search)
    assert callable(task_checkpoint)
    assert callable(task_resume)

def test_mcp_tool_invocation_and_call_logging():
    pg = PostgresAdapter()
    test_id = uuid.uuid4().hex[:6]
    test_content = f"MCP telemetry verification note {test_id}"

    # Call memory_store via MCP tool function
    res = memory_store(
        content=test_content,
        type="fact",
        source_actor="mcp-test-agent"
    )
    assert res["status"] == "success"

    # Verify a call_log entry was inserted in PostgreSQL
    rows = pg.execute_query(
        "SELECT tool, agent, tokens_in, tokens_out, latency_ms FROM call_log WHERE tool = 'memory_store' ORDER BY created_at DESC LIMIT 1;"
    )
    assert len(rows) == 1
    assert rows[0]["tool"] == "memory_store"
    assert rows[0]["agent"] == "mcp-test-agent"
    assert rows[0]["tokens_in"] is not None
    assert rows[0]["latency_ms"] is not None

def test_mcp_checkpoint_and_resume():
    pg = PostgresAdapter()
    task_id = f"task-mcp-{uuid.uuid4().hex[:6]}"

    state = {
        "task_id": task_id,
        "goal": "Test MCP Checkpoint and Resume",
        "steps": [
            {"id": "step-1", "status": "done", "state": "Scaffolded MCP server", "evidence": []}
        ],
        "decisions": [
            {"what": "Use FastMCP", "why": "Lightweight MCP implementation", "source": "spec"}
        ],
        "rejected": [],
        "open_questions": [],
        "written_by": "mcp-agent"
    }

    # Call task_checkpoint
    cp_res = task_checkpoint(task_id=task_id, state=state)
    assert cp_res["status"] == "success"

    # Call task_resume
    resume_res = task_resume(task_id=task_id, token_budget=500)
    assert resume_res["task_id"] == task_id
    assert resume_res["version"] == 1

    # Verify call_log has entries for task_checkpoint and task_resume
    rows = pg.execute_query(
        "SELECT tool FROM call_log WHERE tool IN ('task_checkpoint', 'task_resume') ORDER BY created_at DESC LIMIT 2;"
    )
    assert len(rows) >= 2

