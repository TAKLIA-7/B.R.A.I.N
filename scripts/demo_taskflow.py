"""
Knowledge Brain — Prototype Demonstration Script: TaskFlow API
Simulates a complete real-world multi-agent software engineering lifecycle:
  1. Project Registration & Markdown Scaffolding
  2. Requirement Definition (v1)
  3. Agent Alpha Works & Checkpoints Task Progress
  4. Requirement Evolution (v2: Priority & Due Dates)
  5. Task Staleness Propagation & Agent Beta Handover Resumption
  6. Bug Investigation, Defect Memory, and Prevention
"""
import sys
import os
import json
import time

# Ensure workspace root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.adapters.postgres import PostgresAdapter
from core.project_knowledge.manager import ProjectKnowledgeManager
from core.project_knowledge.schemas import ProjectCreateRequest
from core.evolution.manager import RequirementManager
from core.evolution.schemas import (
    RequirementCreateRequest,
    RequirementProposalRequest,
    RequirementApprovalRequest
)
from core.models.checkpoint import CheckpointState, Step, Decision
from core.handoff.checkpoint import CheckpointService
from core.handoff.resume import ResumeService
from core.bugs.manager import BugManager

pg_adapter = PostgresAdapter()
project_manager = ProjectKnowledgeManager(postgres_adapter=pg_adapter)
req_manager = RequirementManager(postgres_adapter=pg_adapter)
checkpoint_manager = CheckpointService(postgres_adapter=pg_adapter)
resume_manager = ResumeService(postgres_adapter=pg_adapter)
bug_manager = BugManager()

def print_header(title):
    print("\n" + "="*70)
    print(f"  {title.upper()}")
    print("="*70)

def main():
    print_header("Knowledge Brain — Live Prototype Demo: TaskFlow API")
    print("Simulating a full engineering lifecycle across multiple AI agents...")
    time.sleep(1)

    # -------------------------------------------------------------
    # STEP 1: Register Project & Scaffold Knowledge Base
    # -------------------------------------------------------------
    print_header("Step 1: Register Project & Scaffold Knowledge Base")
    project_id = "taskflow_demo"
    p_req = ProjectCreateRequest(
        id=project_id,
        name="TaskFlow API",
        description="Lightweight REST API for collaborative task and todo management"
    )
    proj = project_manager.register_project(p_req)
    print(f"✅ Project Registered: {proj.name} (ID: {proj.id})")
    print(f"📁 Scaffolded Markdown Knowledge Base at: projects/{project_id}/")
    print(f"   ├── PROJECT.md")
    print(f"   ├── architecture/architecture.md")
    print(f"   ├── technical/tech_stack.md")
    print(f"   ├── technical/conventions.md")
    print(f"   └── changelog.md")

    # -------------------------------------------------------------
    # STEP 2: Define Initial Requirement (v1)
    # -------------------------------------------------------------
    print_header("Step 2: Create Requirement REQ-TASK-001 (Version 1)")
    r_create = RequirementCreateRequest(
        req_id="REQ-TASK-001",
        project_id=project_id,
        title="Task Creation and Status API",
        description="Users can create tasks with title, description, and status ('pending', 'completed').",
        category="functional",
        module="tasks"
    )
    req_v1 = req_manager.create_requirement(r_create)
    print(f"✅ Requirement Created: {req_v1.req_id} v{req_v1.current_version}")
    print(f"   Description: '{req_v1.current_description}'")
    print(f"   Status: {req_v1.status}")

    # -------------------------------------------------------------
    # STEP 3: Agent Alpha Implements Feature & Saves Checkpoint
    # -------------------------------------------------------------
    print_header("Step 3: Agent Alpha Works & Saves Checkpoint")
    task_id = "TASK-IMPLEMENT-TASKFLOW-API"
    
    # Associate task with requirement v1
    req_manager.associate_task_with_requirement(task_id, "REQ-TASK-001", 1)

    cp_state = CheckpointState(
        task_id=task_id,
        goal="Implement TaskFlow REST endpoints and database models",
        steps=[
            Step(id="s1", state="Created SQLAlchemy Task model and Pydantic schema", status="done"),
            Step(id="s2", state="Implemented POST /tasks and GET /tasks/{id}", status="done"),
            Step(id="s3", state="Implement PUT /tasks/{id} status update endpoint", status="pending")
        ],
        decisions=[
            Decision(what="Use UUID4 for primary keys", why="Prevent sequential ID enumeration", source="agent_alpha")
        ],
        written_by="agent_alpha"
    )
    cp_res = checkpoint_manager.save_checkpoint(state=cp_state)
    print(f"✅ Checkpoint Saved by Agent Alpha:")
    print(f"   Task ID: {task_id}")
    print(f"   Checkpoint Version: {cp_res['checkpoint_version']}")
    print(f"   Target Requirement: REQ-TASK-001 v1")
    print(f"   Progress: 2/3 steps completed (67%)")

    # -------------------------------------------------------------
    # STEP 4: Requirement Evolves to Version 2
    # -------------------------------------------------------------
    print_header("Step 4: Requirement Evolution — User Adds Priority & Due Dates")
    print("User Request: 'We need task priorities (low, medium, high) and due_date timestamps.'")
    
    # Propose v2
    prop = RequirementProposalRequest(
        req_id="REQ-TASK-001",
        proposed_description="Users can create tasks with title, description, status, priority ('low', 'medium', 'high'), and optional due_date timestamp.",
        reason="Business requirement expansion",
        proposed_by="product_manager"
    )
    p_res = req_manager.propose_version(prop)
    print(f"✅ Version 2 Proposed (Target Version: {p_res['target_version']}, Status: proposed)")
    print(f"   Notice: Version 1 remains live until approval!")

    # Approve v2
    app = RequirementApprovalRequest(
        req_id="REQ-TASK-001",
        target_version=2,
        decision="approved",
        approver="lead_architect",
        rationale="Approved priority & due date schema change"
    )
    app_res = req_manager.approve_version(app)
    print(f"✅ Version 2 Approved by {app_res['approver']}")
    print(f"⚡ AUTOMATIC STALENESS TRIGGER: Flagged active tasks targeting v1 as STALE:")
    for st in app_res["stale_tasks_marked"]:
        print(f"   ⚠️  Marked Stale: {st}")

    # -------------------------------------------------------------
    # STEP 5: Agent Beta Resumes Task (Zero-Waste Handover)
    # -------------------------------------------------------------
    print_header("Step 5: Agent Beta Resumes Task & Receives Staleness Alert")
    print("Agent Alpha is gone. Agent Beta resumes the task using Knowledge Brain...")
    
    resume_pkg = resume_manager.resume_task(task_id, requesting_agent="agent_beta")
    print(f"✅ Handover Package Loaded:")
    print(f"   Previous Agent: {resume_pkg.previous_agent}")
    print(f"   Is Stale Flag: {resume_pkg.is_stale}")
    if resume_pkg.is_stale:
        print(f"\n📢 INJECTED STALENESS WARNING BANNER:")
        print(f"   ------------------------------------------------------------")
        print(f"   {resume_pkg.staleness_warning}")
        print(f"   ------------------------------------------------------------")
    print(f"\n   Completed Steps: {resume_pkg.completed_steps}")
    print(f"   Pending Steps: {resume_pkg.pending_steps}")
    print(f"   Architectural Decisions: {resume_pkg.decisions}")

    # -------------------------------------------------------------
    # STEP 6: Bug Memory & Prevention
    # -------------------------------------------------------------
    print_header("Step 6: Defect Memory & Prevention")
    bug_id = "BUG-TASKFLOW-001"
    b_report = bug_manager.report_bug(
        bug_id=bug_id,
        title="Pydantic ValidationError on ISO-8601 UTC due_date strings with 'Z' suffix",
        symptom="ValueError: Invalid isoformat string: '2026-11-13T12:00:00Z'",
        severity="medium",
        reported_by="agent_beta",
        location={"file": "schemas.py", "line": 18}
    )
    print(f"🐛 Defect Filed: {bug_id} ({b_report['status']})")

    # Record verified fix
    b_fix = bug_manager.record_fix(
        fix_id="FIX-TASKFLOW-001",
        bug_id=bug_id,
        commit="a1b2c3d4e5",
        files_changed=["schemas.py"],
        summary="Use datetime.fromisoformat(due_date.replace('Z', '+00:00')) for Python 3.10 compatibility",
        verification={"test": "test_due_date_parsing.py", "status": "passed"},
        fixed_by="agent_beta"
    )
    print(f"✅ Verified Fix Recorded: {b_fix['fix_id']}")
    print(f"📁 Defect documentation saved to: bug_knowledge/bugs/{bug_id}.md")

    # Immediate semantic search
    search_res = bug_manager.search_bugs("ISO-8601 due date parsing error")
    print(f"\n🔍 Instant Future Bug Retrieval Query: 'ISO-8601 due date parsing error'")
    print(f"   Matched: {search_res[0]['bug_id']} - {search_res[0]['title']} (Status: {search_res[0]['status']})")

    # -------------------------------------------------------------
    # FINAL RECAP
    # -------------------------------------------------------------
    print_header("Demo Summary: What Knowledge Brain Demonstrated")
    print("1. Multi-Model Storage: PostgreSQL (relational core) + pgvector (semantic) + Markdown (human-readable)")
    print("2. Dynamic Evolution: v1 created -> v2 proposed -> v2 approved -> v1 preserved as historical baseline")
    print("3. Task Staleness: Active tasks targeting v1 automatically flagged when v2 approved")
    print("4. Zero-Loss Handover: Agent Beta resumed with exact context and staleness banner without chat replay")
    print("5. Defect Memory: Bug recorded, fix verified, and projected to Markdown for instant retrieval")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
