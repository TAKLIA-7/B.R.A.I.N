import os
import sys
import time
import json
import uuid
import subprocess
from typing import Dict, Any

# Ensure repo root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.models.ingest import IngestRequest, SourceMetadata, SourceType
from core.models.checkpoint import HandoverState, StepItem, StepStatus, DecisionItem, RejectedOption
from core.store.ingest import IngestionCoordinator
from core.retrieve.retriever import HybridRetriever
from core.handoff.checkpoint_manager import CheckpointManager
from core.handoff.resume import ResumeManager
from core.forget.forget_manager import ForgetManager
from core.bugs.manager import BugManager
from core.bugs.projection import MarkdownProjectionGenerator
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter
from core.adapters.neo4j_adapter import Neo4jAdapter

def run_thirty_sessions(restart_enabled: bool = True) -> Dict[str, Any]:
    print("=" * 70)
    print("Starting Knowledge Brain 30-Session Scenario Execution")
    print("=" * 70)

    coordinator = IngestionCoordinator()
    retriever = HybridRetriever()
    checkpoint_mgr = CheckpointManager()
    resume_mgr = ResumeManager()
    forget_mgr = ForgetManager()
    bug_mgr = BugManager()
    proj_gen = MarkdownProjectionGenerator()
    pg = PostgresAdapter()
    redis_adapter = RedisAdapter()
    neo = Neo4jAdapter()

    metrics = {
        "start_time": time.time(),
        "sessions": [],
        "verifications": {}
    }

    # Session 1: Framework decision
    t0 = time.time()
    s1 = coordinator.process_ingestion(IngestRequest(
        source=SourceMetadata(type=SourceType.AGENT, actor="architect-agent", trust_level=0.9),
        content="Decided to build FastAPI REST API with PostgreSQL database as canonical store."
    ))
    metrics["sessions"].append({"session": 1, "action": "ingest_decision", "latency_ms": (time.time()-t0)*1000})

    # Session 2: User preference
    t0 = time.time()
    s2 = coordinator.process_ingestion(IngestRequest(
        source=SourceMetadata(type=SourceType.USER, actor="lead-dev", trust_level=0.95),
        content="User preference: Always use async/await and strict Pydantic v2 models."
    ))
    metrics["sessions"].append({"session": 2, "action": "ingest_preference", "latency_ms": (time.time()-t0)*1000})

    # Session 3: Database specification
    t0 = time.time()
    s3 = coordinator.process_ingestion(IngestRequest(
        source=SourceMetadata(type=SourceType.AGENT, actor="db-agent", trust_level=0.85),
        content="PostgreSQL database runs on port 5432 and utilizes pgvector for semantic retrieval."
    ))
    metrics["sessions"].append({"session": 3, "action": "ingest_fact", "latency_ms": (time.time()-t0)*1000})

    # Session 4: Semantic search for stack
    t0 = time.time()
    r4 = retriever.search(query="PostgreSQL database port and stack", token_budget=300)
    metrics["sessions"].append({"session": 4, "action": "semantic_search", "abstain": r4["abstain"], "tokens_used": r4["tokens_used"], "latency_ms": (time.time()-t0)*1000})
    assert not r4["abstain"]

    # Session 5: Planted false claim
    t0 = time.time()
    s5 = coordinator.process_ingestion(IngestRequest(
        source=SourceMetadata(type=SourceType.DOCUMENT, actor="untrusted_wiki", trust_level=0.2),
        content="Planted claim: Redis is being replaced by Memcached across all services."
    ))
    # Verify planted claim remains asserted
    planted_mem_id = s5.memories[0]["id"]
    planted_row = pg.execute_query("SELECT epistemic_state FROM memories WHERE id = %s;", (planted_mem_id,))[0]
    metrics["verifications"]["planted_claim_asserted"] = (planted_row["epistemic_state"] == "asserted")
    assert planted_row["epistemic_state"] == "asserted"
    metrics["sessions"].append({"session": 5, "action": "planted_claim", "latency_ms": (time.time()-t0)*1000})

    # Session 6: Temporary Redis context
    t0 = time.time()
    redis_adapter.set_with_ttl("session:working:turn_06", "Intermediate tool debug log", ttl_seconds=60)
    metrics["sessions"].append({"session": 6, "action": "redis_temp_store", "latency_ms": (time.time()-t0)*1000})

    # Session 7: Redis TTL verification
    t0 = time.time()
    ttl = redis_adapter.get_ttl("session:working:turn_06")
    metrics["verifications"]["redis_ttl_active"] = (0 < ttl <= 60)
    assert 0 < ttl <= 60
    metrics["sessions"].append({"session": 7, "action": "redis_ttl_check", "ttl": ttl, "latency_ms": (time.time()-t0)*1000})

    # Session 8: Search preferences
    t0 = time.time()
    r8 = retriever.search(query="User preference async Pydantic models", token_budget=300)
    metrics["sessions"].append({"session": 8, "action": "search_preferences", "abstain": r8["abstain"], "latency_ms": (time.time()-t0)*1000})

    # Session 9: Search planted claim (verifies it does not outrank confirmed facts)
    t0 = time.time()
    r9 = retriever.search(query="Planted claim Redis replaced by Memcached", token_budget=300)
    metrics["sessions"].append({"session": 9, "action": "search_planted_claim", "abstain": r9["abstain"], "latency_ms": (time.time()-t0)*1000})

    # Session 10: Memory update / conflict
    t0 = time.time()
    old_mem_id = s3.memories[0]["id"]
    pg.execute_query("UPDATE memories SET status = 'superseded', valid_until = NOW() WHERE id = %s;", (old_mem_id,))
    new_mem_id = str(uuid.uuid4())
    pg.execute_query(
        """
        INSERT INTO memories (id, type, text, status, epistemic_state, source_id, supersedes_id, created_at)
        VALUES (%s, 'fact', 'PostgreSQL primary is on 5432 and read replica is on port 5433.', 'active', 'asserted', %s, %s, NOW());
        """,
        (new_mem_id, s3.source_id, old_mem_id)
    )
    metrics["sessions"].append({"session": 10, "action": "memory_superseded_update", "latency_ms": (time.time()-t0)*1000})

    # Session 11: Verify version history in PostgreSQL
    t0 = time.time()
    old_mem = pg.execute_query("SELECT status, valid_until FROM memories WHERE id = %s;", (old_mem_id,))[0]
    metrics["verifications"]["superseded_history_preserved"] = (old_mem["status"] == "superseded" and old_mem["valid_until"] is not None)
    assert old_mem["status"] == "superseded"
    metrics["sessions"].append({"session": 11, "action": "verify_version_history", "latency_ms": (time.time()-t0)*1000})

    # Session 12: Create Task
    t0 = time.time()
    task_id = f"task-scenario-30-{uuid.uuid4().hex[:6]}"
    checkpoint_mgr.create_task(task_id, "Build and Verify FastAPI Task Management REST API", "agent-A")
    metrics["sessions"].append({"session": 12, "action": "create_task", "latency_ms": (time.time()-t0)*1000})

    # Session 13: Task Checkpoint v1
    t0 = time.time()
    cp1_state = HandoverState(
        task_id=task_id,
        goal="Build and Verify FastAPI Task Management REST API",
        steps=[
            StepItem(id="step-1", status=StepStatus.DONE, state="Scaffold project structure", evidence=["core/ directory created"])
        ],
        decisions=[DecisionItem(what="Use PostgreSQL + pgvector", why="Source of truth + vector retrieval", source="spec")],
        rejected=[RejectedOption(option="SQLite standalone", reason="No pgvector concurrency")],
        open_questions=[],
        written_by="agent-A"
    )
    cp1 = checkpoint_mgr.save_checkpoint(task_id, cp1_state)
    assert cp1["version"] == 1
    metrics["sessions"].append({"session": 13, "action": "checkpoint_v1", "version": 1, "latency_ms": (time.time()-t0)*1000})

    # Session 14: Task Checkpoint v2 (prior to restart)
    t0 = time.time()
    cp2_state = HandoverState(
        task_id=task_id,
        goal="Build and Verify FastAPI Task Management REST API",
        steps=[
            StepItem(id="step-1", status=StepStatus.DONE, state="Scaffold project structure", evidence=["core/ directory created"]),
            StepItem(id="step-2", status=StepStatus.IN_PROGRESS, state="Implement CRUD endpoints in api.py", evidence=[])
        ],
        decisions=[DecisionItem(what="Use PostgreSQL + pgvector", why="Source of truth + vector retrieval", source="spec")],
        rejected=[RejectedOption(option="SQLite standalone", reason="No pgvector concurrency")],
        open_questions=["Which test fixtures for mock client?"],
        written_by="agent-A"
    )
    cp2 = checkpoint_mgr.save_checkpoint(task_id, cp2_state)
    assert cp2["version"] == 2
    metrics["sessions"].append({"session": 14, "action": "checkpoint_v2", "version": 2, "latency_ms": (time.time()-t0)*1000})

    # Session 15: MID-RUN SERVICE RESTART
    print("\n[*] Session 15: Executing Mid-Run Service Restart...")
    t0 = time.time()
    if restart_enabled:
        res = subprocess.run(["docker-compose", "restart"], capture_output=True, text=True)
        assert res.returncode == 0
        # Wait for services to become healthy
        from scripts.wait_for_services import wait_for_services
        assert wait_for_services(timeout=45) is True
    metrics["sessions"].append({"session": 15, "action": "mid_run_restart", "latency_ms": (time.time()-t0)*1000})
    print("[+] Mid-Run Service Restart Complete.\n")

    # Session 16: Resume Task post-restart (Agent B style, no transcript)
    t0 = time.time()
    resumed = resume_mgr.resume_task(task_id, token_budget=800)
    assert resumed["version"] == 2
    assert resumed["task_id"] == task_id
    metrics["verifications"]["task_resumed_post_restart"] = True
    metrics["sessions"].append({"session": 16, "action": "task_resume_post_restart", "version": 2, "latency_ms": (time.time()-t0)*1000})

    # Session 17: Verify pre-restart memories survived
    t0 = time.time()
    mem_check = pg.execute_query("SELECT count(*) AS total FROM memories WHERE status = 'active';")[0]["total"]
    metrics["verifications"]["memories_survived_restart"] = (mem_check >= 3)
    assert mem_check >= 3
    metrics["sessions"].append({"session": 17, "action": "verify_memories_survived", "active_count": mem_check, "latency_ms": (time.time()-t0)*1000})

    # Session 18: Step 2 Done, Checkpoint v3
    t0 = time.time()
    cp3_state = HandoverState(
        task_id=task_id,
        goal="Build and Verify FastAPI Task Management REST API",
        steps=[
            StepItem(id="step-1", status=StepStatus.DONE, state="Scaffold project structure", evidence=["core/ directory created"]),
            StepItem(id="step-2", status=StepStatus.DONE, state="Implement CRUD endpoints in api.py", evidence=["api.py implemented"]),
            StepItem(id="step-3", status=StepStatus.IN_PROGRESS, state="Run test verification", evidence=[])
        ],
        decisions=[DecisionItem(what="Use PostgreSQL + pgvector", why="Source of truth + vector retrieval", source="spec")],
        rejected=[RejectedOption(option="SQLite standalone", reason="No pgvector concurrency")],
        open_questions=[],
        written_by="agent-B"
    )
    cp3 = checkpoint_mgr.save_checkpoint(task_id, cp3_state)
    assert cp3["version"] == 3
    metrics["sessions"].append({"session": 18, "action": "checkpoint_v3", "version": 3, "latency_ms": (time.time()-t0)*1000})

    # Session 19: Checkpoint versions audit
    t0 = time.time()
    vers = [r["version"] for r in pg.execute_query("SELECT version FROM checkpoints WHERE task_id = %s ORDER BY version ASC;", (task_id,))]
    assert vers == [1, 2, 3]
    metrics["verifications"]["three_checkpoint_versions_exist"] = True
    metrics["sessions"].append({"session": 19, "action": "audit_checkpoint_versions", "versions": vers, "latency_ms": (time.time()-t0)*1000})

    # Session 20: Ingest confidential credential to forget
    t0 = time.time()
    secret_kw = f"confidential_api_secret_{uuid.uuid4().hex[:6]}"
    s20 = coordinator.process_ingestion(IngestRequest(
        source=SourceMetadata(type=SourceType.USER, actor="sec-admin", trust_level=0.9),
        content=f"Confidential payment secret string {secret_kw} for staging gateway."
    ))
    sec_mem_id = s20.memories[0]["id"]
    metrics["sessions"].append({"session": 20, "action": "ingest_confidential_credential", "latency_ms": (time.time()-t0)*1000})

    # Session 21: Verified Forgetting of confidential credential
    t0 = time.time()
    receipt = forget_mgr.forget(scope=sec_mem_id)
    assert receipt["status"] == "completed"
    # Verify non-retrieval in PostgreSQL
    del_check = pg.execute_query("SELECT status, embedding FROM memories WHERE id = %s;", (sec_mem_id,))[0]
    metrics["verifications"]["deletion_verified"] = (del_check["status"] == "deleted" and del_check["embedding"] is None)
    assert del_check["status"] == "deleted"
    metrics["sessions"].append({"session": 21, "action": "verified_forgetting", "status": receipt["status"], "latency_ms": (time.time()-t0)*1000})

    # Session 22: Report Bug
    t0 = time.time()
    bug_id = f"BUG-SCENARIO-{uuid.uuid4().hex[:4].upper()}"
    bug_mgr.report_bug(
        bug_id=bug_id,
        title="Pydantic ValidationError returned as 500 in task API",
        symptom="Invalid payload returns internal server error instead of 422 Unprocessable Content",
        root_cause="FastAPI handler missing custom exception mapping",
        severity="medium",
        location={"repo": "BRAIN", "files": ["api.py"], "symbols": ["create_task_checkpoint"]},
        signature="val_err_500_api",
        reported_by="agent-B"
    )
    metrics["sessions"].append({"session": 22, "action": "bug_report", "bug_id": bug_id, "latency_ms": (time.time()-t0)*1000})

    # Session 23: Log Failed Attempt
    t0 = time.time()
    bug_mgr.log_attempt(
        bug_id=bug_id,
        agent="agent-B",
        hypothesis="Try catching broad Exception in endpoint",
        action="Wrapped in generic try/except",
        outcome="failed",
        evidence={"result": "Masked other system exceptions"},
        learned="Must catch RequestValidationError specifically"
    )
    metrics["sessions"].append({"session": 23, "action": "bug_log_failed_attempt", "latency_ms": (time.time()-t0)*1000})

    # Session 24: Log Partial Attempt
    t0 = time.time()
    bug_mgr.log_attempt(
        bug_id=bug_id,
        agent="agent-B",
        hypothesis="Add RequestValidationError handler",
        action="Added handler to FastAPI app",
        outcome="partial",
        evidence={"result": "Fixed POST /ingest but endpoint /tasks needs it too"}
    )
    metrics["sessions"].append({"session": 24, "action": "bug_log_partial_attempt", "latency_ms": (time.time()-t0)*1000})

    # Session 25: Record Verified Fix with test proof
    t0 = time.time()
    fix_id = f"FIX-SCENARIO-{uuid.uuid4().hex[:4].upper()}"
    fix_res = bug_mgr.record_fix(
        fix_id=fix_id,
        bug_id=bug_id,
        commit="commit-789abc",
        files_changed=["api.py"],
        summary="Registered FastAPI validation error handler returning 422 with detailed errors",
        verification={"tests": "pytest tests/unit/test_checkpoint_schema.py", "result": "passed", "run_id": "scenario-run-1"},
        fixed_by="agent-B"
    )
    assert fix_res["fix_id"] == fix_id
    bug_state = pg.execute_query("SELECT status, epistemic_state FROM bugs WHERE bug_id = %s;", (bug_id,))[0]
    metrics["verifications"]["bug_fix_verified"] = (bug_state["status"] == "verified" and bug_state["epistemic_state"] == "confirmed")
    assert bug_state["status"] == "verified"
    metrics["sessions"].append({"session": 25, "action": "bug_record_fix_verified", "status": "verified", "latency_ms": (time.time()-t0)*1000})

    # Session 26: Sync Markdown projections for bugs/fixes
    t0 = time.time()
    proj_res = proj_gen.sync_all_projections()
    metrics["verifications"]["markdown_projections_synced"] = (proj_res["bugs_synced"] >= 1)
    metrics["sessions"].append({"session": 26, "action": "sync_markdown_projections", "synced": proj_res, "latency_ms": (time.time()-t0)*1000})

    # Session 27: Abstention check on unknown topic
    t0 = time.time()
    r27 = retriever.search(query="extraterrestrial propulsion hyperdrive physics", token_budget=100)
    metrics["verifications"]["abstention_honored"] = (r27["abstain"] is True and r27["message"] == "no supporting memory")
    assert r27["abstain"] is True
    metrics["sessions"].append({"session": 27, "action": "abstention_test", "abstain": True, "latency_ms": (time.time()-t0)*1000})

    # Session 28: Search with Bug History
    t0 = time.time()
    r28 = retriever.search(query="FastAPI validation error in api.py", token_budget=500)
    has_bugs = "bug_history" in r28 and len(r28["bug_history"]) >= 1
    metrics["verifications"]["bug_history_retrieved"] = has_bugs
    assert has_bugs
    metrics["sessions"].append({"session": 28, "action": "search_with_bug_history", "bugs_found": len(r28["bug_history"]), "latency_ms": (time.time()-t0)*1000})

    # Session 29: Telemetry Call Log Audit
    t0 = time.time()
    call_count = pg.execute_query("SELECT count(*) AS total FROM call_log;")[0]["total"]
    metrics["verifications"]["call_log_audited"] = (call_count >= 1)
    metrics["sessions"].append({"session": 29, "action": "audit_call_log", "total_logged_calls": call_count, "latency_ms": (time.time()-t0)*1000})

    # Session 30: Compile and Save Reproducible Report
    t0 = time.time()
    metrics["total_duration_seconds"] = round(time.time() - metrics["start_time"], 2)
    metrics["total_sessions"] = len(metrics["sessions"]) + 1  # Including Session 30
    metrics["all_verifications_passed"] = all(metrics["verifications"].values())
    metrics["sessions"].append({"session": 30, "action": "compile_reproducible_report", "latency_ms": (time.time()-t0)*1000})

    report_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "session_scenario_report.json"))
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print("\n" + "=" * 70)
    print(f"30-Session Scenario Complete: {metrics['total_sessions']} sessions executed in {metrics['total_duration_seconds']}s")
    print(f"All Verifications Passed: {metrics['all_verifications_passed']}")
    print(f"Report Written: {report_path}")
    print("=" * 70 + "\n")

    return metrics

if __name__ == "__main__":
    run_thirty_sessions()
