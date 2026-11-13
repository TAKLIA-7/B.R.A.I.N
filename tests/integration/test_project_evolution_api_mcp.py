import uuid
import pytest
from fastapi.testclient import TestClient
from api import app
from mcp_server import (
    project_register,
    project_get,
    project_context,
    project_documents_list,
    requirement_propose,
    requirement_approve,
    requirement_get,
    requirement_history,
    requirement_impact,
    requirement_check_staleness
)

client = TestClient(app)

def test_project_and_requirement_rest_api_lifecycle():
    pid = f"rest-proj-{uuid.uuid4().hex[:6]}"
    req_id = f"REQ-REST-{uuid.uuid4().hex[:4].upper()}"

    # 1. POST /projects
    p_resp = client.post("/projects", json={
        "id": pid,
        "name": "Cloud Platform",
        "description": "Multi-tenant cloud platform"
    })
    assert p_resp.status_code == 200
    p_data = p_resp.json()
    assert p_data["id"] == pid
    assert p_data["name"] == "Cloud Platform"

    # 2. GET /projects/{project_id}
    p_get = client.get(f"/projects/{pid}")
    assert p_get.status_code == 200
    assert p_get.json()["id"] == pid

    # 3. GET /projects/{project_id}/documents
    docs_get = client.get(f"/projects/{pid}/documents")
    assert docs_get.status_code == 200
    docs = docs_get.json()
    assert len(docs) >= 9

    # 4. POST /requirements/create
    r_create = client.post("/requirements/create", json={
        "req_id": req_id,
        "project_id": pid,
        "module": "billing",
        "title": "Subscription Billing",
        "description": "Stripe recurring billing with webhook handlers",
        "acceptance_criteria": ["Handle invoice.paid", "Handle payment_failed"],
        "created_by": "Billing PM",
        "initial_status": "approved"
    })
    assert r_create.status_code == 200
    assert r_create.json()["req_id"] == req_id
    assert r_create.json()["current_version"] == 1

    # 5. POST /requirements/propose (v2)
    r_prop = client.post("/requirements/propose", json={
        "req_id": req_id,
        "proposed_description": "Stripe recurring billing with metered usage and tax calculation.",
        "acceptance_criteria": ["Calculate metered seats", "Automatic sales tax"],
        "reason": "Enterprise customer requirement",
        "proposed_by": "Enterprise Agent"
    })
    assert r_prop.status_code == 200
    assert r_prop.json()["target_version"] == 2
    assert r_prop.json()["status"] == "proposed"

    # 6. GET /requirements/{req_id}/impact
    impact_get = client.get(f"/requirements/{req_id}/impact?version=2")
    assert impact_get.status_code == 200
    assert "billing" in impact_get.json()["affected_modules"]

    # 7. POST /requirements/{req_id}/approve (Approve v2)
    r_app = client.post(f"/requirements/{req_id}/approve", json={
        "req_id": req_id,
        "target_version": 2,
        "decision": "approved",
        "approver": "VP Engineering",
        "rationale": "Enterprise tier launch ready"
    })
    assert r_app.status_code == 200
    assert r_app.json()["decision"] == "approved"

    # 8. GET /requirements/{req_id}/history
    hist_get = client.get(f"/requirements/{req_id}/history")
    assert hist_get.status_code == 200
    history = hist_get.json()
    assert len(history) == 2
    assert history[0]["approval_status"] == "superseded"
    assert history[1]["approval_status"] == "approved"

    # 9. GET /projects/{project_id}/context
    ctx_get = client.get(f"/projects/{pid}/context?task=Implement%20Billing")
    assert ctx_get.status_code == 200
    ctx_data = ctx_get.json()
    assert ctx_data["project_id"] == pid
    assert req_id in ctx_data["context_markdown"]

def test_mcp_project_and_evolution_tools():
    pid = f"mcp-proj-{uuid.uuid4().hex[:6]}"
    req_id = f"REQ-MCP-{uuid.uuid4().hex[:4].upper()}"

    # 1. project_register
    p = project_register(id=pid, name="FastMCP Service", description="Demonstrates MCP Project evolution")
    assert p["id"] == pid

    # 2. project_get
    p_info = project_get(pid)
    assert p_info["name"] == "FastMCP Service"

    # 3. project_documents_list
    docs = project_documents_list(pid)
    assert len(docs) >= 9

    # 4. requirement_propose (Initial creation via proposal tool)
    item = requirement_propose(
        req_id=req_id,
        title="Zero Trust Auth",
        description="mTLS and OAuth2 service-to-service auth",
        project_id=pid,
        module="security",
        proposed_by="Security PM"
    )
    assert item["success"] is True
    assert item["action"] == "created"

    # 5. requirement_propose (Upgrade to v2)
    upg = requirement_propose(
        req_id=req_id,
        proposed_description="mTLS with SPIFFE/SPIRE x509 workload identity attestations",
        reason="Zero-trust federation upgrade",
        proposed_by="SecOps Agent"
    )
    assert upg["success"] is True
    assert upg["action"] == "proposed"
    assert upg["target_version"] == 2

    # 6. requirement_impact
    imp = requirement_impact(req_id, version=2)
    assert "security" in imp["affected_modules"]

    # 7. requirement_approve
    app_res = requirement_approve(
        req_id=req_id,
        target_version=2,
        decision="approved",
        approver="CISO"
    )
    assert app_res["decision"] == "approved"

    # 8. requirement_get & requirement_history
    req_info = requirement_get(req_id)
    assert req_info["current_version"] == 2
    hist = requirement_history(req_id)
    assert len(hist) == 2

    # 9. project_context
    ctx = project_context(project_id=pid, task="Zero Trust Architecture", token_budget=2000)
    assert req_id in ctx["context_markdown"]

