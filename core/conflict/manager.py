"""
core/conflict/manager.py
Authoritative orchestrator for Human-in-the-Loop Conflict Resolution in Knowledge Brain.
Enforces deterministic mandatory approval rules, human authorization gates, optimistic concurrency,
PostgreSQL canonical execution, transactional outbox sync, and Markdown documentation updates.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from core.adapters.postgres import PostgresAdapter
from core.jev.engine import JEVDecisionEngine
from core.conflict.schemas import (
    ConflictState,
    ConflictResolution,
    ConflictApprovalItem,
    HumanApprovalAction
)
from core.conflict.rules import MandatoryApprovalEvaluator
from core.conflict.detector import ConflictDetector
from core.project_knowledge.synchronizer import ProjectDocumentSynchronizer
from core.store.outbox import OutboxProcessor

logger = logging.getLogger(__name__)


class ConflictManager:
    """
    Coordinates conflict detection, human approval workflows, authorization enforcement,
    and post-approval knowledge synchronization.
    """

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        jev_engine: Optional[JEVDecisionEngine] = None,
        synchronizer: Optional[ProjectDocumentSynchronizer] = None,
        outbox_processor: Optional[OutboxProcessor] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.jev = jev_engine or JEVDecisionEngine(postgres_adapter=self.pg)
        self.detector = ConflictDetector(postgres_adapter=self.pg)
        self.sync = synchronizer or ProjectDocumentSynchronizer(postgres_adapter=self.pg)
        self.outbox = outbox_processor or OutboxProcessor(postgres_adapter=self.pg)

    def check_and_register_conflict(
        self,
        incoming_claim: str,
        source_actor: str = "agent",
        source_type: str = "agent",
        trust_level: float = 0.5,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[ConflictApprovalItem]]:
        """
        Evaluates incoming claim against existing memories and requirements.
        If a contradiction is detected and mandatory approval conditions are met,
        registers a pending conflict without updating canonical memories.
        """
        # 1. Search existing candidates
        existing_mems = self.detector.find_candidate_memories(incoming_claim)
        conflicting_reqs = self.detector.find_conflicting_requirements(incoming_claim, project_id=project_id)

        if not existing_mems and not conflicting_reqs:
            # No contradiction detected
            return False, None

        # 2. Consult JEV for proposed resolution
        top_mem = existing_mems[0] if existing_mems else {
            "id": "req-conflict", "text": conflicting_reqs[0]["title"], "trust_score": 0.9
        }
        try:
            jev_decision, _ = self.jev.decide_conflict(
                existing_memory=top_mem,
                new_claim=incoming_claim,
                new_trust_level=trust_level
            )
            proposed_res = jev_decision.resolution
            jev_confidence = 0.7 if jev_decision.assigned_epistemic_state == "disputed" else 0.9
        except Exception as e:
            logger.warning(f"JEV decide_conflict error: {e}")
            proposed_res = "dispute"
            jev_confidence = 0.5

        # 3. Evaluate deterministic mandatory approval rules
        req_approval, rule_ids, reasons = MandatoryApprovalEvaluator.evaluate(
            incoming_claim=incoming_claim,
            existing_memories=existing_mems,
            conflicting_requirements=conflicting_reqs,
            evidence_and_provenance=evidence,
            jev_proposed_resolution=proposed_res,
            new_trust_level=trust_level,
            jev_confidence=jev_confidence
        )

        if not req_approval:
            # Clear unambiguous contradiction that can be resolved automatically
            return False, None

        # 4. Mandatory human approval is required!
        conflict_id = f"conf_{uuid.uuid4().hex[:10]}"
        affected_docs = self.detector.identify_affected_documents(incoming_claim)
        affected_reqs = [r["req_id"] for r in conflicting_reqs]
        primary_reason = "; ".join(reasons)

        mem_ids = [str(m["id"]) for m in existing_mems]
        snapshot = {
            "existing_memories": [
                {"id": str(m["id"]), "text": m["text"], "epistemic_state": m.get("epistemic_state", "asserted")}
                for m in existing_mems
            ],
            "conflicting_requirements": [
                {"req_id": r["req_id"], "title": r["title"]}
                for r in conflicting_reqs
            ]
        }

        # Insert pending conflict into PostgreSQL
        sql = """
            INSERT INTO memory_conflicts (
                id, project_id, existing_memory_ids, incoming_claim, source_agent,
                source_session, evidence_and_provenance, proposed_resolution,
                reason_approval_required, applicable_rule_ids, potentially_affected_documents,
                potentially_affected_requirements, potentially_affected_tasks, status,
                execution_status, synchronization_status, existing_state_snapshot,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', 'pending', %s, NOW(), NOW())
            RETURNING id, project_id, incoming_claim, proposed_resolution, status, created_at;
        """
        self.pg.execute_query(sql, (
            conflict_id,
            project_id,
            json.dumps(mem_ids),
            incoming_claim,
            source_actor,
            session_id,
            json.dumps(evidence or {}),
            proposed_res,
            primary_reason,
            json.dumps(rule_ids),
            json.dumps(affected_docs),
            json.dumps(affected_reqs),
            json.dumps([]),
            ConflictState.PENDING_HUMAN_APPROVAL.value,
            json.dumps(snapshot, default=str)
        ))

        # Log audit entry
        self._log_audit(
            conflict_id=conflict_id,
            actor=source_actor,
            actor_type="agent",
            action="conflict_detected",
            decision=None,
            rationale=primary_reason,
            prev_status=None,
            new_status=ConflictState.PENDING_HUMAN_APPROVAL.value
        )

        item = self.get_conflict(conflict_id)
        return True, item

    def list_pending_approvals(self, project_id: Optional[str] = None) -> List[ConflictApprovalItem]:
        """Lists all conflicts currently awaiting human arbitration."""
        sql = """
            SELECT id, project_id, existing_memory_ids, incoming_claim, source_agent,
                   source_session, evidence_and_provenance, proposed_resolution,
                   reason_approval_required, applicable_rule_ids, potentially_affected_documents,
                   potentially_affected_requirements, potentially_affected_tasks, status,
                   human_approver, approval_rationale, clarification_request, clarification_response,
                   execution_status, synchronization_status, existing_state_snapshot,
                   created_at, updated_at
            FROM memory_conflicts
            WHERE status IN ('pending_human_approval', 'clarification_required')
        """
        params = []
        if project_id:
            sql += " AND project_id = %s"
            params.append(project_id)
        sql += " ORDER BY created_at DESC;"

        rows = self.pg.execute_query(sql, tuple(params))
        items: List[ConflictApprovalItem] = []
        for r in rows:
            items.append(self._row_to_item(r))
        return items

    def get_conflict(self, conflict_id: str) -> Optional[ConflictApprovalItem]:
        """Retrieves complete details of a specific conflict."""
        sql = """
            SELECT id, project_id, existing_memory_ids, incoming_claim, source_agent,
                   source_session, evidence_and_provenance, proposed_resolution,
                   reason_approval_required, applicable_rule_ids, potentially_affected_documents,
                   potentially_affected_requirements, potentially_affected_tasks, status,
                   human_approver, approval_rationale, clarification_request, clarification_response,
                   execution_status, synchronization_status, existing_state_snapshot,
                   created_at, updated_at
            FROM memory_conflicts
            WHERE id = %s;
        """
        rows = self.pg.execute_query(sql, (conflict_id,))
        if not rows:
            return None
        return self._row_to_item(rows[0])

    def submit_clarification(
        self,
        conflict_id: str,
        author: str,
        clarification_notes: str,
        updated_claim: Optional[str] = None,
        additional_evidence: Optional[Dict[str, Any]] = None
    ) -> ConflictApprovalItem:
        """
        Submits clarification or additional evidence for a pending conflict.
        Conflict remains pending; silence or timeout is never assumed as approval.
        """
        conflict = self.get_conflict(conflict_id)
        if not conflict:
            raise ValueError(f"Conflict '{conflict_id}' not found.")

        combined_evidence = dict(conflict.evidence_and_provenance or {})
        if additional_evidence:
            combined_evidence.update(additional_evidence)

        claim_to_check = updated_claim or conflict.incoming_claim

        # Re-evaluate rules with new clarification
        conflicting_reqs = self.detector.find_conflicting_requirements(claim_to_check, project_id=conflict.project_id)
        existing_mems = conflict.existing_state_snapshot.get("existing_memories", [])
        req_approval, rule_ids, reasons = MandatoryApprovalEvaluator.evaluate(
            incoming_claim=claim_to_check,
            existing_memories=existing_mems,
            conflicting_requirements=conflicting_reqs,
            evidence_and_provenance=combined_evidence,
            jev_proposed_resolution=conflict.proposed_resolution
        )

        new_status = ConflictState.PENDING_HUMAN_APPROVAL.value if req_approval else ConflictState.EVALUATING.value

        sql = """
            UPDATE memory_conflicts
            SET clarification_response = %s,
                incoming_claim = %s,
                evidence_and_provenance = %s,
                applicable_rule_ids = %s,
                reason_approval_required = %s,
                status = %s,
                updated_at = NOW()
            WHERE id = %s;
        """
        self.pg.execute_query(sql, (
            clarification_notes,
            claim_to_check,
            json.dumps(combined_evidence),
            json.dumps(rule_ids),
            "; ".join(reasons) if reasons else conflict.reason_approval_required,
            new_status,
            conflict_id
        ))

        self._log_audit(
            conflict_id=conflict_id,
            actor=author,
            actor_type="agent" if "agent" in author.lower() else "human",
            action="clarification_submitted",
            decision=None,
            rationale=clarification_notes,
            prev_status=conflict.status,
            new_status=new_status
        )

        return self.get_conflict(conflict_id)

    def approve_conflict(
        self,
        conflict_id: str,
        approver: str,
        rationale: Optional[str] = None,
        selected_resolution: Optional[str] = None,
        is_human: bool = True
    ) -> Dict[str, Any]:
        """
        Approves a pending conflict.
        Enforces human authorization (AI agents are strictly forbidden from approving their own conflicts).
        Applies optimistic concurrency to prevent stale approvals and synchronizes derived stores & docs.
        """
        # 1. Authorization check
        if not is_human or "agent" in approver.lower():
            raise PermissionError("Unauthorized: AI agents must not approve their own ambiguous conflicts. Only authorized humans may approve.")

        conflict = self.get_conflict(conflict_id)
        if not conflict:
            raise ValueError(f"Conflict '{conflict_id}' not found.")

        # 2. Status check
        if conflict.status not in [ConflictState.PENDING_HUMAN_APPROVAL.value, ConflictState.CLARIFICATION_REQUIRED.value, ConflictState.EVALUATING.value]:
            raise ValueError(f"Conflict '{conflict_id}' cannot be approved: current status is '{conflict.status}'.")

        # 3. Optimistic concurrency check (ensure existing memories haven't changed status)
        for mem_id in conflict.existing_memory_ids:
            cur_rows = self.pg.execute_query("SELECT status FROM memories WHERE id = %s;", (mem_id,))
            if cur_rows and cur_rows[0]["status"] != "active":
                raise ValueError(f"Stale approval conflict: target memory '{mem_id}' has already been modified or superseded.")

        # 4. Determine final resolution
        resolution = selected_resolution or conflict.proposed_resolution
        if resolution not in [r.value for r in ConflictResolution]:
            raise ValueError(f"Invalid resolution '{resolution}'. Must be one of: supersede, dispute, coexist, reject.")

        # 5. Execute approved action in PostgreSQL
        new_memory_id = str(uuid.uuid4())
        old_mem_id = conflict.existing_memory_ids[0] if conflict.existing_memory_ids else None

        if resolution == ConflictResolution.SUPERSEDE.value:
            # Supersede old memory
            if old_mem_id:
                self.pg.execute_query("""
                    UPDATE memories
                    SET status = 'superseded', valid_until = NOW()
                    WHERE id = %s;
                """, (old_mem_id,))
            # Insert new canonical active memory
            self.pg.execute_query("""
                INSERT INTO memories (
                    id, type, text, status, epistemic_state, valid_from, supersedes_id, created_at
                )
                VALUES (%s, 'decision', %s, 'active', 'confirmed', NOW(), %s, NOW());
            """, (new_memory_id, conflict.incoming_claim, old_mem_id))

            # Synchronize derived vector and graph via outbox
            self.outbox.enqueue_event("sync_vector", {"memory_id": new_memory_id, "text": conflict.incoming_claim})
            self.outbox.process_pending_events()

        elif resolution == ConflictResolution.DISPUTE.value:
            if old_mem_id:
                self.pg.execute_query("UPDATE memories SET epistemic_state = 'disputed' WHERE id = %s;", (old_mem_id,))
            self.pg.execute_query("""
                INSERT INTO memories (id, type, text, status, epistemic_state, created_at)
                VALUES (%s, 'decision', %s, 'active', 'disputed', NOW());
            """, (new_memory_id, conflict.incoming_claim))

        elif resolution == ConflictResolution.COEXIST.value:
            self.pg.execute_query("""
                INSERT INTO memories (id, type, text, status, epistemic_state, created_at)
                VALUES (%s, 'fact', %s, 'active', 'confirmed', NOW());
            """, (new_memory_id, conflict.incoming_claim))

        # 6. Update project Markdown documents if project_id exists
        sync_status = "completed"
        if conflict.project_id:
            for doc in conflict.potentially_affected_documents:
                self._update_markdown_projection(conflict.project_id, doc, conflict.incoming_claim, approver)

        # 7. Update memory_conflicts table
        sql_update = """
            UPDATE memory_conflicts
            SET status = 'resolved',
                human_approver = %s,
                approval_rationale = %s,
                proposed_resolution = %s,
                execution_status = 'executed',
                synchronization_status = %s,
                updated_at = NOW()
            WHERE id = %s;
        """
        self.pg.execute_query(sql_update, (
            approver, rationale or "Approved by authorized human", resolution, sync_status, conflict_id
        ))

        # 8. Log audit entry
        self._log_audit(
            conflict_id=conflict_id,
            actor=approver,
            actor_type="human",
            action="approved",
            decision=resolution,
            rationale=rationale,
            prev_status=conflict.status,
            new_status=ConflictState.RESOLVED.value
        )

        return {
            "success": True,
            "conflict_id": conflict_id,
            "status": "resolved",
            "resolution": resolution,
            "approver": approver,
            "new_memory_id": new_memory_id
        }

    def reject_conflict(
        self,
        conflict_id: str,
        approver: str,
        rationale: str,
        is_human: bool = True
    ) -> Dict[str, Any]:
        """
        Rejects a proposed conflict change.
        Existing canonical memories remain active and unchanged.
        The rejected claim is NEVER synchronized to derived stores or Markdown documents.
        """
        # Authorization check
        if not is_human or "agent" in approver.lower():
            raise PermissionError("Unauthorized: AI agents must not reject or resolve conflicts autonomously.")

        conflict = self.get_conflict(conflict_id)
        if not conflict:
            raise ValueError(f"Conflict '{conflict_id}' not found.")

        if conflict.status not in [ConflictState.PENDING_HUMAN_APPROVAL.value, ConflictState.CLARIFICATION_REQUIRED.value, ConflictState.EVALUATING.value]:
            raise ValueError(f"Conflict '{conflict_id}' cannot be rejected: current status is '{conflict.status}'.")

        # Update conflict status to rejected
        sql_update = """
            UPDATE memory_conflicts
            SET status = 'rejected',
                human_approver = %s,
                approval_rationale = %s,
                execution_status = 'rejected',
                synchronization_status = 'not_applicable',
                updated_at = NOW()
            WHERE id = %s;
        """
        self.pg.execute_query(sql_update, (approver, rationale, conflict_id))

        # Log audit entry
        self._log_audit(
            conflict_id=conflict_id,
            actor=approver,
            actor_type="human",
            action="rejected",
            decision="reject",
            rationale=rationale,
            prev_status=conflict.status,
            new_status=ConflictState.REJECTED.value
        )

        return {
            "success": True,
            "conflict_id": conflict_id,
            "status": "rejected",
            "approver": approver,
            "rationale": rationale,
            "canonical_knowledge_preserved": True
        }

    def _update_markdown_projection(self, project_id: str, doc_rel_path: str, claim: str, approver: str) -> None:
        """Appends human-approved decision note to affected project Markdown document."""
        try:
            pdir = self.sync.get_project_dir(project_id)
            abs_path = os.path.join(pdir, doc_rel_path)
            content = self.sync.read_file(abs_path) or f"# {doc_rel_path}\n"
            note = f"\n\n## [Approved Change - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}]\n- **Decision:** {claim}\n- **Approved By:** `{approver}`\n"
            self.sync.sync_document(project_id, doc_rel_path, "architecture_decision", content + note, force=False)
        except Exception as e:
            logger.warning(f"Could not update markdown projection {doc_rel_path}: {e}")

    def _log_audit(
        self,
        conflict_id: str,
        actor: str,
        actor_type: str,
        action: str,
        decision: Optional[str],
        rationale: Optional[str],
        prev_status: Optional[str],
        new_status: str
    ) -> None:
        """Appends record to conflict_audit_log table."""
        sql = """
            INSERT INTO conflict_audit_log (
                conflict_id, actor, actor_type, action, decision,
                rationale, previous_status, new_status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW());
        """
        try:
            self.pg.execute_query(sql, (
                conflict_id, actor, actor_type, action, decision, rationale, prev_status, new_status
            ))
        except Exception as e:
            logger.warning(f"Could not log conflict audit: {e}")

    def _row_to_item(self, row: Dict[str, Any]) -> ConflictApprovalItem:
        mem_ids = row.get("existing_memory_ids") or []
        if isinstance(mem_ids, str):
            try:
                mem_ids = json.loads(mem_ids)
            except Exception:
                mem_ids = []

        rules = row.get("applicable_rule_ids") or []
        if isinstance(rules, str):
            try:
                rules = json.loads(rules)
            except Exception:
                rules = []

        docs = row.get("potentially_affected_documents") or []
        if isinstance(docs, str):
            try:
                docs = json.loads(docs)
            except Exception:
                docs = []

        reqs = row.get("potentially_affected_requirements") or []
        if isinstance(reqs, str):
            try:
                reqs = json.loads(reqs)
            except Exception:
                reqs = []

        tasks = row.get("potentially_affected_tasks") or []
        if isinstance(tasks, str):
            try:
                tasks = json.loads(tasks)
            except Exception:
                tasks = []

        ev = row.get("evidence_and_provenance") or {}
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except Exception:
                ev = {}

        snap = row.get("existing_state_snapshot") or {}
        if isinstance(snap, str):
            try:
                snap = json.loads(snap)
            except Exception:
                snap = {}

        return ConflictApprovalItem(
            conflict_id=row["id"],
            project_id=row.get("project_id"),
            existing_memory_ids=mem_ids,
            incoming_claim=row["incoming_claim"],
            source_agent=row["source_agent"],
            source_session=row.get("source_session"),
            evidence_and_provenance=ev,
            proposed_resolution=row["proposed_resolution"],
            reason_approval_required=row["reason_approval_required"],
            applicable_rule_ids=rules,
            potentially_affected_documents=docs,
            potentially_affected_requirements=reqs,
            potentially_affected_tasks=tasks,
            status=row["status"],
            human_approver=row.get("human_approver"),
            approval_rationale=row.get("approval_rationale"),
            clarification_request=row.get("clarification_request"),
            clarification_response=row.get("clarification_response"),
            execution_status=row.get("execution_status", "pending"),
            synchronization_status=row.get("synchronization_status", "pending"),
            existing_state_snapshot=snap,
            created_at=str(row["created_at"]) if row.get("created_at") else None,
            updated_at=str(row["updated_at"]) if row.get("updated_at") else None
        )
