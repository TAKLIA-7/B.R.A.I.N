import os
import uuid
import pytest
from core.adapters.postgres import PostgresAdapter
from core.evolution.manager import RequirementManager
from core.evolution.schemas import (
    RequirementCreateRequest,
    RequirementProposalRequest,
    RequirementApprovalRequest
)
from core.project_knowledge.manager import ProjectKnowledgeManager
from core.project_knowledge.schemas import ProjectCreateRequest
from core.handoff.checkpoint import CheckpointService
from core.handoff.resume import ResumeService
from core.handoff.schemas import CheckpointState, CheckpointStep, CheckpointDecision

@pytest.fixture
def pg():
    return PostgresAdapter()

@pytest.fixture
def req_manager(pg):
    return RequirementManager(postgres_adapter=pg)

@pytest.fixture
def proj_manager(pg):
    return ProjectKnowledgeManager(postgres_adapter=pg)

@pytest.fixture
def checkpoint_service(pg):
    return CheckpointService(postgres_adapter=pg)

@pytest.fixture
def resume_service(pg):
    return ResumeService(postgres_adapter=pg)

def test_1_new_project_registration(proj_manager):
    """Phase 8 Test 1: Register a project, scaffold Markdown directory, verify document registry."""
    pid = f"proj-{uuid.uuid4().hex[:6]}"
    req = ProjectCreateRequest(
        id=pid,
        name="E-Commerce Platform",
        description="Scalable microservices e-commerce platform",
        repository_url="https://github.com/example/ecommerce"
    )
    p = proj_manager.register_project(req)
    assert p.id == pid
    assert p.name == "E-Commerce Platform"

    # Verify Markdown files exist on disk
    pdir = proj_manager.sync.get_project_dir(pid)
    assert os.path.exists(os.path.join(pdir, "PROJECT.md"))
    assert os.path.exists(os.path.join(pdir, "changelog.md"))
    assert os.path.exists(os.path.join(pdir, "architecture/system_architecture.md"))
    assert os.path.exists(os.path.join(pdir, "architecture/database_design.md"))
    assert os.path.exists(os.path.join(pdir, "technical/tech_stack.md"))

    # Verify documents registered in PostgreSQL
    docs = proj_manager.list_documents(pid)
    assert len(docs) >= 9
    rel_paths = {d.relative_path for d in docs}
    assert "PROJECT.md" in rel_paths
    assert "technical/tech_stack.md" in rel_paths
    assert all(d.status == "synced" for d in docs)

def test_2_technology_stack_update_and_changelog(proj_manager):
    """Phase 8 Test 2: Update technology stack, verify tech_stack.md and changelog updates."""
    pid = f"proj-{uuid.uuid4().hex[:6]}"
    proj_manager.register_project(ProjectCreateRequest(id=pid, name="Analytics Engine"))

    # Update tech stack
    new_stack = {
        "Language": "Python 3.12",
        "Framework": "FastAPI",
        "Database": "PostgreSQL 16 with pgvector",
        "Cache": "Redis Stack"
    }
    updated = proj_manager.update_tech_stack(pid, new_stack, author="Lead Architect")
    assert updated is True

    # Verify content updated on disk
    doc = proj_manager.get_document(pid, "technical/tech_stack.md")
    assert "PostgreSQL 16 with pgvector" in doc["content"]
    assert doc["version"] >= 2

    # Verify changelog has entry
    changelog_doc = proj_manager.get_document(pid, "changelog.md")
    assert "Updated technology stack definition" in changelog_doc["content"]

def test_3_requirement_evolution_proposal_and_approval(req_manager, proj_manager):
    """Phase 8 Test 3: Create REQ v1, propose v2 (unapproved), approve v2, verify version transition."""
    pid = f"proj-{uuid.uuid4().hex[:6]}"
    proj_manager.register_project(ProjectCreateRequest(id=pid, name="Auth Service"))

    req_id = f"REQ-AUTH-{uuid.uuid4().hex[:4].upper()}"

    # 1. Create REQ v1 (Approved)
    create_req = RequirementCreateRequest(
        req_id=req_id,
        project_id=pid,
        module="auth",
        title="User Authentication",
        description="Email and password login returning JWT access tokens.",
        acceptance_criteria=["Valid credentials return 200 and access_token", "Invalid credentials return 401"],
        created_by="Product Owner",
        initial_status="approved"
    )
    req_item = req_manager.create_requirement(create_req)
    assert req_item.req_id == req_id
    assert req_item.current_version == 1
    assert req_item.status == "approved"
    assert len(req_item.versions) == 1
    assert req_item.versions[0].approval_status == "approved"

    # Sync to Markdown
    proj_manager.sync_requirement_doc(pid, req_id, req_item.model_dump(), [v.model_dump() for v in req_item.versions])

    # 2. Agent proposes v2 (Add refresh tokens and rotation)
    proposal = RequirementProposalRequest(
        req_id=req_id,
        proposed_description="Email/password login with JWT access tokens AND refresh token rotation.",
        acceptance_criteria=["Refresh tokens stored in Redis with 7-day TTL", "Used refresh tokens immediately invalidated"],
        reason="Security compliance: prevent indefinite token replay",
        proposed_by="Security Agent"
    )
    prop_res = req_manager.propose_version(proposal)
    assert prop_res["success"] is True
    assert prop_res["target_version"] == 2
    assert prop_res["status"] == "proposed"

    # CRITICAL INVARIANT: Active requirement MUST STILL BE v1
    cur_req = req_manager.get_requirement(req_id)
    assert cur_req.current_version == 1
    assert cur_req.status == "approved"

    # Verify v2 exists in history as 'proposed'
    history = req_manager.get_requirement_history(req_id)
    assert len(history) == 2
    assert history[0].version == 1 and history[0].approval_status == "approved"
    assert history[1].version == 2 and history[1].approval_status == "proposed"

    # 3. Authorized user approves v2
    app_res = req_manager.approve_version(RequirementApprovalRequest(
        req_id=req_id,
        target_version=2,
        decision="approved",
        approver="Chief Architect",
        rationale="Approved for Q4 security release"
    ))
    assert app_res["success"] is True
    assert app_res["decision"] == "approved"

    # Verify v2 is now active and v1 is superseded
    updated_req = req_manager.get_requirement(req_id)
    assert updated_req.current_version == 2
    history_after = req_manager.get_requirement_history(req_id)
    assert history_after[0].approval_status == "superseded"
    assert history_after[1].approval_status == "approved"
    assert history_after[1].approved_by == "Chief Architect"

def test_4_architecture_decision_adr(proj_manager):
    """Phase 8 Test 4: Create ADR-001, create superseding ADR-002, verify index."""
    pid = f"proj-{uuid.uuid4().hex[:6]}"
    proj_manager.register_project(ProjectCreateRequest(id=pid, name="ADR Project"))

    # Create ADR-001
    proj_manager.record_decision_adr(
        project_id=pid,
        decision_id="ADR-001",
        title="Use Symmetric HMAC-SHA256 for JWT",
        context="Initial simple authentication needed",
        decision="Use shared secret with HS256",
        consequences="Simple to implement but key distribution to other services is hard",
        author="Dev A"
    )

    # Supersede with ADR-002
    proj_manager.record_decision_adr(
        project_id=pid,
        decision_id="ADR-002",
        title="Migrate to Asymmetric Ed25519 for JWT",
        context="Multiple services now verify tokens independently",
        decision="Use Ed25519 public/private keypair",
        consequences="Public key can be distributed safely via JWKS endpoint",
        author="Security Lead",
        supersedes="ADR-001"
    )

    doc1 = proj_manager.get_document(pid, "decisions/ADR-001.md")
    doc2 = proj_manager.get_document(pid, "decisions/ADR-002.md")
    assert doc1 is not None and "ADR-001" in doc1["content"]
    assert doc2 is not None and "ADR-001" in doc2["content"] and "Supersedes" in doc2["content"]

    index_doc = proj_manager.get_document(pid, "decisions/index.md")
    assert "ADR-001" in index_doc["content"]
    assert "ADR-002" in index_doc["content"]

def test_5_agent_handover_with_staleness_warning(req_manager, proj_manager, checkpoint_service, resume_service):
    """
    Phase 8 Test 6:
    1. Agent A starts task targeting Requirement v1.
    2. Agent A saves checkpoint.
    3. Requirement is upgraded and approved to v2.
    4. Knowledge Brain marks task as stale.
    5. Agent B resumes task and receives staleness warning & v2 delta!
    """
    pid = f"proj-{uuid.uuid4().hex[:6]}"
    proj_manager.register_project(ProjectCreateRequest(id=pid, name="Handover Project"))
    req_id = f"REQ-AUTH-{uuid.uuid4().hex[:4].upper()}"

    # Create REQ v1
    req_manager.create_requirement(RequirementCreateRequest(
        req_id=req_id,
        project_id=pid,
        module="auth",
        title="Auth System",
        description="JWT authentication access tokens.",
        created_by="User"
    ))

    task_id = f"TASK-{uuid.uuid4().hex[:6]}"
    checkpoint_service.create_task(
        task_id=task_id,
        goal="Implement JWT Authentication",
        created_by="Agent A"
    )
    # Associate task with REQ v1
    req_manager.associate_task_with_requirement(task_id, req_id, version=1)

    # Agent A checkpoints
    state_v1 = CheckpointState(
        task_id=task_id,
        goal="Implement JWT Authentication",
        steps=[CheckpointStep(id="login", status="done", state="Login implemented", evidence=[])],
        decisions=[CheckpointDecision(what="JWT", why="Stateless", source="spec")],
        rejected=[],
        open_questions=[],
        written_by="Agent A",
        project_files=["api.py"]
    )
    checkpoint_service.save_checkpoint(state_v1)

    # Requirement upgraded to v2 and approved
    req_manager.propose_version(RequirementProposalRequest(
        req_id=req_id,
        proposed_description="JWT authentication with refresh token rotation.",
        reason="Security upgrade",
        proposed_by="Security Architect"
    ))
    req_manager.approve_version(RequirementApprovalRequest(
        req_id=req_id,
        target_version=2,
        decision="approved",
        approver="Lead"
    ))

    # Verify task was marked stale
    staleness = req_manager.check_task_staleness(task_id)
    assert staleness.is_stale is True
    assert staleness.latest_requirement_version == 2
    assert staleness.target_requirement_version == 1

    # Agent B resumes
    resume_context = resume_service.resume_task(task_id, requesting_agent="Agent B")
    assert resume_context.is_stale is True
    assert "STALE" in resume_context.handover_context
    assert req_id in resume_context.handover_context

def test_6_manual_markdown_change_conflict_detection(proj_manager):
    """Phase 8 Test 7: Detect manual human edit to Markdown and avoid silent overwrite."""
    pid = f"proj-{uuid.uuid4().hex[:6]}"
    proj_manager.register_project(ProjectCreateRequest(id=pid, name="Manual Edit Project"))

    pdir = proj_manager.sync.get_project_dir(pid)
    arch_path = os.path.join(pdir, "architecture/system_architecture.md")

    # Simulate human developer editing the file directly
    with open(arch_path, "a", encoding="utf-8") as f:
        f.write("\n## Custom Human Note\nManually added microservice guideline.\n")

    # Attempt automatic sync without force
    success, status = proj_manager.sync.sync_document(
        pid,
        "architecture/system_architecture.md",
        "architecture",
        "# Auto Generated Architecture\nAttempted automated overwrite\n",
        force=False
    )
    # Must flag conflict and NOT overwrite!
    assert success is False
    assert status == "conflict"

    # Verify human edit was preserved
    with open(arch_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Custom Human Note" in content

def test_7_project_isolation(proj_manager):
    """Phase 8 Test 9: Verify multiple projects maintain isolated documentation and contexts."""
    pid1 = f"proj-a-{uuid.uuid4().hex[:4]}"
    pid2 = f"proj-b-{uuid.uuid4().hex[:4]}"

    proj_manager.register_project(ProjectCreateRequest(id=pid1, name="Project Alpha"))
    proj_manager.register_project(ProjectCreateRequest(id=pid2, name="Project Beta"))

    ctx1 = proj_manager.get_project_context(pid1)
    ctx2 = proj_manager.get_project_context(pid2)

    assert "Project Alpha" in ctx1.context_markdown
    assert "Project Beta" not in ctx1.context_markdown

    assert "Project Beta" in ctx2.context_markdown
    assert "Project Alpha" not in ctx2.context_markdown
