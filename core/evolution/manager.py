import json
import uuid
import re
import logging
from typing import Dict, Any, List, Optional
from core.adapters.postgres import PostgresAdapter
from core.evolution.schemas import (
    RequirementCreateRequest,
    RequirementProposalRequest,
    RequirementApprovalRequest,
    RequirementItem,
    RequirementVersionItem,
    RequirementImpact,
    ChangeRequestItem,
    TaskStalenessReport
)

logger = logging.getLogger(__name__)

class RequirementManager:
    """
    Authoritative manager for requirements, immutable versioning,
    change detection, approval workflows, impact analysis, and agent staleness sync.
    """

    def __init__(self, postgres_adapter: Optional[PostgresAdapter] = None):
        self.pg = postgres_adapter or PostgresAdapter()

    def create_requirement(self, req: RequirementCreateRequest) -> RequirementItem:
        """Creates a new canonical requirement and its initial version (v1)."""
        req_uuid = str(uuid.uuid4())
        version_uuid = str(uuid.uuid4())
        initial_version = 1

        is_approved = (req.initial_status == "approved")
        version_status = "approved" if is_approved else "proposed"
        approved_by = req.created_by if is_approved else None

        with self.pg.get_connection() as conn:
            with conn.cursor() as cur:
                # 1. Insert into requirements table
                insert_req_sql = """
                    INSERT INTO requirements (id, req_id, project_id, module, title, category, priority, current_version, status, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    RETURNING id, req_id, project_id, module, title, category, priority, current_version, status, created_at, updated_at;
                """
                cur.execute(insert_req_sql, (
                    req_uuid, req.req_id, req.project_id, req.module, req.title,
                    req.category, req.priority, initial_version, req.initial_status
                ))
                req_row = cur.fetchone()

                # 2. Insert Version 1
                insert_ver_sql = """
                    INSERT INTO requirement_versions (
                        id, requirement_id, version, description, acceptance_criteria,
                        source, created_by, created_at, approval_status, approved_by, approved_at, supersedes_version
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, NOW(), %s, %s, CASE WHEN %s THEN NOW() ELSE NULL END, NULL)
                    RETURNING id, requirement_id, version, description, acceptance_criteria, source, created_by, created_at, approval_status;
                """
                cur.execute(insert_ver_sql, (
                    version_uuid, req_uuid, initial_version, req.description,
                    json.dumps(req.acceptance_criteria), "user_specification",
                    req.created_by, version_status, approved_by, is_approved
                ))

        # 3. Compute and store initial impacts
        self.compute_and_store_impact(req.req_id, initial_version, req.module, req.description)

        return self.get_requirement(req.req_id)

    def propose_version(self, proposal: RequirementProposalRequest) -> Dict[str, Any]:
        """
        Proposes a new version for an existing requirement.
        Preserves previous versions and never overwrites current active version until approved.
        """
        req_rows = self.pg.execute_query(
            "SELECT id, req_id, module, current_version, status FROM requirements WHERE req_id = %s;",
            (proposal.req_id,)
        )
        if not req_rows:
            raise ValueError(f"Requirement '{proposal.req_id}' not found.")

        req = req_rows[0]
        req_uuid = req["id"]
        current_version = req["current_version"]
        target_version = current_version + 1

        # Fetch current description
        cur_desc_rows = self.pg.execute_query(
            "SELECT description FROM requirement_versions WHERE requirement_id = %s AND version = %s;",
            (req_uuid, current_version)
        )
        original_desc = cur_desc_rows[0]["description"] if cur_desc_rows else ""

        version_uuid = str(uuid.uuid4())
        change_id = f"CR-{proposal.req_id}-v{target_version}"

        with self.pg.get_connection() as conn:
            with conn.cursor() as cur:
                # 1. Insert proposed requirement version (unapproved)
                insert_ver_sql = """
                    INSERT INTO requirement_versions (
                        id, requirement_id, version, description, acceptance_criteria,
                        source, created_by, created_at, approval_status, supersedes_version
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, NOW(), 'proposed', %s)
                    ON CONFLICT (requirement_id, version) DO UPDATE SET
                        description = EXCLUDED.description,
                        acceptance_criteria = EXCLUDED.acceptance_criteria;
                """
                cur.execute(insert_ver_sql, (
                    version_uuid, req_uuid, target_version, proposal.proposed_description,
                    json.dumps(proposal.acceptance_criteria), proposal.source or "agent_proposal",
                    proposal.proposed_by, current_version
                ))

                # 2. Insert change request
                insert_cr_sql = """
                    INSERT INTO change_requests (
                        id, change_id, req_id, target_version, original_value, proposed_value,
                        reason, source, proposed_by, status, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'proposed', NOW())
                    ON CONFLICT (change_id) DO UPDATE SET
                        proposed_value = EXCLUDED.proposed_value,
                        reason = EXCLUDED.reason;
                """
                cur.execute(insert_cr_sql, (
                    str(uuid.uuid4()), change_id, proposal.req_id, target_version,
                    original_desc, proposal.proposed_description, proposal.reason,
                    proposal.source, proposal.proposed_by
                ))

        # 3. Compute and store impact analysis for the proposed version
        impact = self.compute_and_store_impact(
            proposal.req_id, target_version, req["module"], proposal.proposed_description
        )

        return {
            "success": True,
            "req_id": proposal.req_id,
            "target_version": target_version,
            "change_id": change_id,
            "status": "proposed",
            "impact": impact.model_dump()
        }

    def approve_version(self, approval: RequirementApprovalRequest) -> Dict[str, Any]:
        """
        Authorizes or rejects a proposed requirement version.
        On approval:
          - Marks version approved
          - Marks older approved version superseded
          - Updates requirement current_version
          - Records approval audit record
          - Marks affected agent tasks as stale!
        """
        req_rows = self.pg.execute_query(
            "SELECT id, req_id, current_version FROM requirements WHERE req_id = %s;",
            (approval.req_id,)
        )
        if not req_rows:
            raise ValueError(f"Requirement '{approval.req_id}' not found.")

        req = req_rows[0]
        req_uuid = req["id"]
        change_id = f"CR-{approval.req_id}-v{approval.target_version}"

        with self.pg.get_connection() as conn:
            with conn.cursor() as cur:
                if approval.decision == "approved":
                    # 1. Update previous approved version to superseded
                    cur.execute("""
                        UPDATE requirement_versions
                        SET approval_status = 'superseded'
                        WHERE requirement_id = %s AND approval_status = 'approved';
                    """, (req_uuid,))

                    # 2. Update target version to approved
                    cur.execute("""
                        UPDATE requirement_versions
                        SET approval_status = 'approved',
                            approved_by = %s,
                            approved_at = NOW()
                        WHERE requirement_id = %s AND version = %s;
                    """, (approval.approver, req_uuid, approval.target_version))

                    # 3. Update requirement current_version and status
                    cur.execute("""
                        UPDATE requirements
                        SET current_version = %s,
                            status = 'approved',
                            updated_at = NOW()
                        WHERE id = %s;
                    """, (approval.target_version, req_uuid))

                    # 4. Update change request status
                    cur.execute("""
                        UPDATE change_requests
                        SET status = 'applied'
                        WHERE change_id = %s;
                    """, (change_id,))

                else:
                    # Rejected
                    cur.execute("""
                        UPDATE requirement_versions
                        SET approval_status = 'rejected'
                        WHERE requirement_id = %s AND version = %s;
                    """, (req_uuid, approval.target_version))

                    cur.execute("""
                        UPDATE change_requests
                        SET status = 'rejected'
                        WHERE change_id = %s;
                    """, (change_id,))

                # 5. Insert change approval audit log
                cur.execute("""
                    INSERT INTO change_approvals (id, change_id, decision, approver, rationale, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW());
                """, (
                    str(uuid.uuid4()), change_id, approval.decision,
                    approval.approver, approval.rationale or f"Decision: {approval.decision}"
                ))

        # 6. If approved, synchronize staleness across affected tasks
        stale_tasks = []
        if approval.decision == "approved":
            stale_tasks = self.mark_tasks_stale_for_requirement(approval.req_id, approval.target_version)

        return {
            "success": True,
            "req_id": approval.req_id,
            "target_version": approval.target_version,
            "decision": approval.decision,
            "approver": approval.approver,
            "stale_tasks_marked": stale_tasks
        }

    def get_requirement(self, req_id: str) -> Optional[RequirementItem]:
        """Fetches current approved requirement with version history."""
        req_rows = self.pg.execute_query(
            "SELECT * FROM requirements WHERE req_id = %s;",
            (req_id,)
        )
        if not req_rows:
            return None

        r = req_rows[0]
        versions = self.get_requirement_history(req_id)

        # Find current description from current_version
        current_desc = ""
        current_criteria = []
        for v in versions:
            if v.version == r["current_version"]:
                current_desc = v.description
                current_criteria = v.acceptance_criteria
                break

        return RequirementItem(
            id=str(r["id"]),
            req_id=r["req_id"],
            project_id=r.get("project_id"),
            module=r["module"],
            title=r["title"],
            category=r["category"],
            priority=r["priority"],
            current_version=r["current_version"],
            status=r["status"],
            created_at=str(r["created_at"]),
            updated_at=str(r["updated_at"]),
            current_description=current_desc,
            acceptance_criteria=current_criteria,
            versions=versions
        )

    def get_requirement_history(self, req_id: str) -> List[RequirementVersionItem]:
        """Returns all historical and proposed versions of a requirement ordered by version asc."""
        sql = """
            SELECT rv.*
            FROM requirement_versions rv
            JOIN requirements r ON rv.requirement_id = r.id
            WHERE r.req_id = %s
            ORDER BY rv.version ASC;
        """
        rows = self.pg.execute_query(sql, (req_id,))
        results = []
        for r in rows:
            criteria = r.get("acceptance_criteria", [])
            if isinstance(criteria, str):
                try:
                    criteria = json.loads(criteria)
                except Exception:
                    criteria = []

            results.append(RequirementVersionItem(
                id=str(r["id"]),
                requirement_id=str(r["requirement_id"]),
                version=r["version"],
                description=r["description"],
                acceptance_criteria=criteria,
                source=r.get("source"),
                created_by=r["created_by"],
                created_at=str(r["created_at"]),
                approval_status=r["approval_status"],
                approved_by=r.get("approved_by"),
                approved_at=str(r["approved_at"]) if r.get("approved_at") else None,
                supersedes_version=r.get("supersedes_version")
            ))
        return results

    def compute_and_store_impact(
        self,
        req_id: str,
        version: int,
        module: str,
        description: str
    ) -> RequirementImpact:
        """
        Computes impact analysis for a requirement version:
        identifies affected modules, files, API endpoints, tasks, and test files.
        """
        combined = f"{module} {description}".lower()

        # 1. Modules
        modules = [module]
        for candidate in ["auth", "users", "api", "database", "billing", "notifications"]:
            if candidate in combined and candidate not in modules:
                modules.append(candidate)

        # 2. Files
        files = []
        if "auth" in combined:
            files.extend(["api.py", "core/auth.py", "demo_api/main.py", "demo_api/models.py"])
        if "token" in combined:
            files.append("core/tokens.py")
        if "database" in combined or "postgres" in combined:
            files.append("core/adapters/postgres.py")

        # 3. Endpoints
        endpoints = []
        if "login" in combined or "auth" in combined:
            endpoints.extend(["POST /auth/login", "POST /auth/register"])
        if "refresh" in combined or "rotation" in combined:
            endpoints.append("POST /auth/refresh")

        # 4. Entities
        entities = []
        if "user" in combined:
            entities.append("User")
        if "token" in combined:
            entities.append("RefreshToken")

        # 5. Affected Tests
        tests = []
        if "auth" in combined or "token" in combined:
            tests.extend(["tests/scenarios/test_fastapi_task_api.py", "tests/integration/test_task_api.py"])

        # 6. Affected tasks in PostgreSQL
        affected_tasks = []
        task_rows = self.pg.execute_query(
            "SELECT id FROM tasks WHERE target_requirement_id = %s OR goal ILIKE %s LIMIT 10;",
            (req_id, f"%{module}%")
        )
        for t in task_rows:
            affected_tasks.append(t["id"])

        impact_id = str(uuid.uuid4())
        sql = """
            INSERT INTO requirement_impacts (
                id, req_id, version, affected_modules, affected_files,
                affected_endpoints, affected_entities, affected_tasks, affected_tests, created_at
            )
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, NOW())
            RETURNING id;
        """
        self.pg.execute_query(sql, (
            impact_id, req_id, version, json.dumps(modules), json.dumps(files),
            json.dumps(endpoints), json.dumps(entities), json.dumps(affected_tasks), json.dumps(tests)
        ))

        return RequirementImpact(
            req_id=req_id,
            version=version,
            affected_modules=modules,
            affected_files=files,
            affected_endpoints=endpoints,
            affected_entities=entities,
            affected_tasks=affected_tasks,
            affected_tests=tests
        )

    def mark_tasks_stale_for_requirement(self, req_id: str, new_version: int) -> List[str]:
        """
        Scans all active tasks working against older versions of this requirement
        and marks them `is_stale = True`.
        """
        sql = """
            UPDATE tasks
            SET is_stale = TRUE,
                updated_at = NOW()
            WHERE (target_requirement_id = %s AND (target_requirement_version IS NULL OR target_requirement_version < %s))
            RETURNING id;
        """
        rows = self.pg.execute_query(sql, (req_id, new_version))
        stale_ids = [r["id"] for r in rows]
        if stale_ids:
            logger.info(f"Marked {len(stale_ids)} tasks as stale due to {req_id} upgrade to v{new_version}: {stale_ids}")
        return stale_ids

    def check_task_staleness(self, task_id: str) -> TaskStalenessReport:
        """Determines if a task's requirement context is stale."""
        rows = self.pg.execute_query(
            "SELECT id, target_requirement_id, target_requirement_version, is_stale FROM tasks WHERE id = %s;",
            (task_id,)
        )
        if not rows:
            return TaskStalenessReport(task_id=task_id, is_stale=False, reason="Task not found")

        t = rows[0]
        req_id = t.get("target_requirement_id")
        target_ver = t.get("target_requirement_version")

        if not req_id:
            return TaskStalenessReport(task_id=task_id, is_stale=t.get("is_stale", False), reason="No requirement associated")

        req = self.get_requirement(req_id)
        if not req:
            return TaskStalenessReport(task_id=task_id, is_stale=False, reason=f"Requirement {req_id} not found")

        is_stale = (target_ver is None) or (target_ver < req.current_version) or t.get("is_stale", False)
        reason = None
        if is_stale:
            reason = f"Task was targeting {req_id} v{target_ver or 1}, but current approved version is v{req.current_version}."

        return TaskStalenessReport(
            task_id=task_id,
            is_stale=is_stale,
            target_requirement_id=req_id,
            target_requirement_version=target_ver,
            latest_requirement_version=req.current_version,
            reason=reason
        )

    def associate_task_with_requirement(self, task_id: str, req_id: str, version: Optional[int] = None) -> None:
        """Associates an agent task with a specific requirement version."""
        if version is None:
            req = self.get_requirement(req_id)
            version = req.current_version if req else 1

        self.pg.execute_query("""
            UPDATE tasks
            SET target_requirement_id = %s,
                target_requirement_version = %s,
                is_stale = FALSE,
                updated_at = NOW()
            WHERE id = %s;
        """, (req_id, version, task_id))

