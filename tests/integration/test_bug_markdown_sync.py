import pytest
import os
import uuid
import shutil
from core.bugs.manager import BugManager
from core.bugs.projection import MarkdownProjectionGenerator
from core.adapters.postgres import PostgresAdapter

def test_bug_and_failed_attempts_lifecycle():
    bm = BugManager()
    pg = PostgresAdapter()
    
    bug_id = f"BUG-TDD-{uuid.uuid4().hex[:6].upper()}"
    bm.report_bug(
        bug_id=bug_id,
        title="Async dead-lock in connection pool acquire",
        symptom="Requests hang indefinitely under concurrent load",
        root_cause="Missing timeout on pool lock acquire",
        severity="high",
        location={"repo": "BRAIN", "files": ["core/db/session.py"], "symbols": ["get_db_session"]},
        signature="async_deadlock_session_pool",
        reported_by="tester-agent"
    )

    # Log a FAILED attempt
    att1 = bm.log_attempt(
        bug_id=bug_id,
        agent="debugger-agent",
        hypothesis="Threadpool queue full",
        action="Increased max_workers",
        outcome="failed",
        evidence={"result": "Still hanging"},
        learned="Deadlock is at async lock level, not threadpool"
    )
    assert att1["outcome"] == "failed"

    # Log a PARTIAL attempt
    att2 = bm.log_attempt(
        bug_id=bug_id,
        agent="debugger-agent",
        hypothesis="Async lock not released on exception",
        action="Wrapped in try-finally block",
        outcome="partial",
        evidence={"result": "Hangs reduced but still occur on timeout"},
        learned="Lock needs explicit timeout parameter"
    )
    assert att2["outcome"] == "partial"

    # Record verified fix
    fix_id = f"FIX-TDD-{uuid.uuid4().hex[:6].upper()}"
    fix = bm.record_fix(
        fix_id=fix_id,
        bug_id=bug_id,
        commit="abc1234",
        files_changed=["core/db/session.py"],
        summary="Added async timeout to pool acquire and enforced try-finally release",
        verification={"tests": "pytest tests/integration/test_infrastructure.py", "result": "passed", "run_id": "run-99"},
        fixed_by="fixer-agent"
    )
    assert fix["fix_id"] == fix_id

    # Verify history in PostgreSQL
    history = bm.get_bug_history(bug_id)
    assert history["bug"]["status"] == "verified"
    assert len(history["attempts"]) == 2
    assert history["attempts"][0]["outcome"] == "failed"
    assert history["attempts"][1]["outcome"] == "partial"
    assert len(history["fixes"]) == 1
    assert len(history["events"]) >= 3  # reported, 2 attempts, fix

def test_markdown_projection_generation_and_regeneration():
    bm = BugManager()
    proj = MarkdownProjectionGenerator()
    
    bug_id = f"BUG-PROJ-{uuid.uuid4().hex[:6].upper()}"
    fix_id = f"FIX-PROJ-{uuid.uuid4().hex[:6].upper()}"

    bm.report_bug(
        bug_id=bug_id,
        title="Uncaught ValidationError on invalid payload",
        symptom="500 Internal Server Error instead of 422",
        root_cause="Missing FastAPI exception handler for Pydantic ValidationError",
        severity="medium",
        location={"repo": "BRAIN", "files": ["api.py"]},
        signature="val_error_500",
        reported_by="qa-agent"
    )

    bm.log_attempt(
        bug_id=bug_id,
        agent="qa-agent",
        hypothesis="FastAPI default handler disabled",
        action="Inspected middleware stack",
        outcome="failed",
        evidence={"result": "Middleware stack was default"}
    )

    bm.record_fix(
        fix_id=fix_id,
        bug_id=bug_id,
        commit="def5678",
        files_changed=["api.py"],
        summary="Added explicit RequestValidationError exception handler",
        verification={"tests": "pytest tests/integration/test_ingestion_api.py", "result": "passed", "run_id": "run-101"},
        fixed_by="qa-agent"
    )

    # Generate Markdown projections
    generated = proj.sync_all_projections()
    assert generated["bugs_synced"] >= 1
    assert generated["fixes_synced"] >= 1

    bug_file = os.path.join(proj.bugs_dir, f"{bug_id}.md")
    fix_file = os.path.join(proj.fixes_dir, f"{fix_id}.md")

    assert os.path.exists(bug_file), f"Bug file not found: {bug_file}"
    assert os.path.exists(fix_file), f"Fix file not found: {fix_file}"

    # Verify Markdown file content contains YAML front matter and failed attempt
    with open(bug_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert f"id: {bug_id}" in content
    assert "status: verified" in content
    assert "Investigation Attempts" in content
    assert "FAILED" in content
    assert fix_id in content

    # Test Regeneration: Delete files and ensure sync_all_projections restores them
    os.remove(bug_file)
    os.remove(fix_file)
    assert not os.path.exists(bug_file)

    proj.sync_all_projections()
    assert os.path.exists(bug_file)
    assert os.path.exists(fix_file)

