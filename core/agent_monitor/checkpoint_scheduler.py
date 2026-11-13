"""
core/agent_monitor/checkpoint_scheduler.py
Coordinates proactive agent checkpointing, Git inspection, PostgreSQL persistence,
Markdown synchronization for `checkpoint.md`, and audit logging.
"""
import logging
import threading
import uuid
from typing import Dict, Any, Optional, List, Tuple
from core.adapters.postgres import PostgresAdapter
from core.handoff.checkpoint import CheckpointService
from core.handoff.schemas import CheckpointState, CheckpointStep, CheckpointDecision
from core.project_knowledge.synchronizer import ProjectDocumentSynchronizer
from core.agent_monitor.base_adapter import AgentUsageMetrics, TriggerReason
from core.agent_monitor.usage_monitor import UsageMonitor, CheckpointPolicy
from core.agent_monitor.git_inspector import GitInspector
from core.agent_monitor.checkpoint_generator import CheckpointMarkdownGenerator

logger = logging.getLogger(__name__)


class CheckpointScheduler:
    """
    Central scheduler and execution engine for proactive AI agent checkpointing.
    Supports Mode A (agent-assisted) and Mode B (host-side automated).
    """

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        checkpoint_service: Optional[CheckpointService] = None,
        synchronizer: Optional[ProjectDocumentSynchronizer] = None,
        usage_monitor: Optional[UsageMonitor] = None,
        repo_path: Optional[str] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.checkpoint_service = checkpoint_service or CheckpointService(postgres_adapter=self.pg)
        self.sync = synchronizer or ProjectDocumentSynchronizer(postgres_adapter=self.pg)
        self.monitor = usage_monitor or UsageMonitor()
        self.git_inspector = GitInspector(repo_path=repo_path)
        self._lock = threading.Lock()
        self._task_locks: Dict[str, threading.Lock] = {}

    def _get_task_lock(self, task_id: str) -> threading.Lock:
        with self._lock:
            if task_id not in self._task_locks:
                self._task_locks[task_id] = threading.Lock()
            return self._task_locks[task_id]

    def resolve_project_id(self, task_id: str, explicit_project_id: Optional[str] = None) -> str:
        """Resolves project ID for a task, checking DB linkage or falling back cleanly."""
        if explicit_project_id:
            return explicit_project_id

        # Check PostgreSQL tasks table
        try:
            rows = self.pg.execute_query("SELECT project_id FROM tasks WHERE id = %s;", (task_id,))
            if rows and rows[0].get("project_id"):
                return rows[0]["project_id"]
        except Exception as e:
            logger.debug(f"Could not resolve project_id from tasks table: {e}")

        # Check if any registered project matches
        try:
            projs = self.pg.execute_query("SELECT id FROM projects LIMIT 10;")
            for p in projs:
                pid = p["id"]
                if pid in task_id or task_id.startswith(pid):
                    return pid
            if projs:
                return projs[0]["id"]
        except Exception:
            pass

        return "default"

    def _fetch_related_bugs_and_fixes(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        bugs = []
        fixes = []
        try:
            with self.pg.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT bug_id, title, symptom, root_cause, severity, status
                        FROM bugs
                        WHERE status IN ('open', 'investigating')
                        ORDER BY first_seen DESC LIMIT 5;
                    """)
                    for b in cur.fetchall():
                        bugs.append({
                            "bug_id": b[0], "title": b[1], "symptom": b[2],
                            "root_cause": b[3], "severity": b[4], "status": b[5]
                        })
                    cur.execute("""
                        SELECT fix_id, bug_id, summary, verified_at
                        FROM fixes
                        ORDER BY verified_at DESC LIMIT 5;
                    """)
                    for f in cur.fetchall():
                        fixes.append({
                            "fix_id": f[0], "bug_id": f[1], "summary": f[2]
                        })
        except Exception as e:
            logger.debug(f"Error querying bugs/fixes for checkpoint: {e}")
        return bugs, fixes

    def _record_audit_trigger(
        self,
        task_id: str,
        project_id: str,
        agent_name: str,
        trigger_reason: str,
        session_id: Optional[str] = None,
        context_percentage: Optional[float] = None,
        tokens_consumed: Optional[int] = None,
        tokens_capacity: Optional[int] = None,
        checkpoint_version: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        status: str = "completed",
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Records checkpoint trigger into checkpoint_triggers table."""
        sql = """
            INSERT INTO checkpoint_triggers (
                id, task_id, project_id, agent_name, session_id,
                trigger_reason, context_percentage, tokens_consumed, tokens_capacity,
                checkpoint_version, idempotency_key, status, details, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (idempotency_key) DO UPDATE SET
                status = EXCLUDED.status,
                details = EXCLUDED.details;
        """
        import json
        det_json = json.dumps(details or {})
        try:
            self.pg.execute_query(sql, (
                str(uuid.uuid4()),
                task_id,
                project_id,
                agent_name,
                session_id,
                trigger_reason,
                context_percentage,
                tokens_consumed,
                tokens_capacity,
                checkpoint_version,
                idempotency_key,
                status,
                det_json
            ))
        except Exception as e:
            logger.warning(f"Could not record checkpoint trigger audit: {e}")

    def execute_checkpoint(
        self,
        task_id: str,
        state: Optional[CheckpointState] = None,
        project_id: Optional[str] = None,
        trigger_reason: str = "manual",
        session_id: Optional[str] = None,
        agent_name: str = "agent",
        metrics: Optional[AgentUsageMetrics] = None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes complete checkpointing workflow:
        1. Persists state to PostgreSQL (canonical).
        2. Gathers Git status/diffs.
        3. Updates project `checkpoint.md` atomically with conflict detection.
        4. Preserves versioned checkpoint file (`checkpoints/checkpoint_v{N}.md`).
        5. Records audit event in PostgreSQL.
        """
        task_lock = self._get_task_lock(task_id)
        with task_lock:
            p_id = self.resolve_project_id(task_id, project_id)

            # Ensure valid CheckpointState
            if state is None:
                # Mode B: Host-side state recovery from latest known checkpoint
                latest_cp = self.checkpoint_service.get_latest_checkpoint(task_id)
                if latest_cp:
                    state_json = latest_cp["state_json"]
                    state = CheckpointState.model_validate(state_json)
                else:
                    # Construct minimal default state
                    state = CheckpointState(
                        task_id=task_id,
                        goal="Ongoing task execution",
                        steps=[CheckpointStep(id="init", status="in_progress", state="Task initialized")],
                        decisions=[],
                        rejected=[],
                        written_by=agent_name
                    )

            # 1. Gather Git working tree status
            git_state = self.git_inspector.inspect()
            if git_state.commit and not state.git_commit:
                state.git_commit = git_state.commit
            if git_state.branch and not state.git_branch:
                state.git_branch = git_state.branch

            # 2. Persist to PostgreSQL (canonical store of truth)
            save_res = self.checkpoint_service.save_checkpoint(state=state)
            version = save_res["checkpoint_version"]

            # Link project_id in tasks table if available
            try:
                self.pg.execute_query(
                    "UPDATE tasks SET project_id = %s WHERE id = %s;",
                    (p_id, task_id)
                )
            except Exception:
                pass

            # 3. Query bugs and fixes
            bugs, fixes = self._fetch_related_bugs_and_fixes()

            # 4. Generate Markdown projection for checkpoint.md
            md_content = CheckpointMarkdownGenerator.generate_checkpoint_md(
                state=state,
                project_id=p_id,
                checkpoint_version=version,
                trigger_reason=trigger_reason,
                session_id=session_id,
                git_state=git_state,
                bugs=bugs,
                fixes=fixes
            )

            # 5. Synchronize checkpoint.md via ProjectDocumentSynchronizer
            sync_ok, sync_status = self.sync.sync_document(
                project_id=p_id,
                relative_path="checkpoint.md",
                document_type="checkpoint",
                content=md_content,
                force=False
            )

            # 6. Preserve historical copy in checkpoints/checkpoint_v{N}.md
            self.sync.sync_document(
                project_id=p_id,
                relative_path=f"checkpoints/checkpoint_v{version}.md",
                document_type="checkpoint_history",
                content=md_content,
                force=True
            )

            # 7. Record audit trigger
            pct = metrics.get_effective_usage_percentage() if metrics else None
            t_consumed = metrics.tokens_consumed if metrics else None
            t_cap = metrics.context_window_capacity if metrics else None
            idem_key = idempotency_key or f"{task_id}:{trigger_reason}:v{version}"

            self._record_audit_trigger(
                task_id=task_id,
                project_id=p_id,
                agent_name=agent_name,
                session_id=session_id,
                trigger_reason=trigger_reason,
                context_percentage=pct,
                tokens_consumed=t_consumed,
                tokens_capacity=t_cap,
                checkpoint_version=version,
                idempotency_key=idem_key,
                status="completed" if sync_ok else f"conflict_detected:{sync_status}",
                details={
                    "sync_status": sync_status,
                    "uncommitted_files": git_state.uncommitted_changes_count,
                    "git_branch": git_state.branch,
                    "git_commit": git_state.commit
                }
            )

            return {
                "success": True,
                "task_id": task_id,
                "project_id": p_id,
                "checkpoint_version": version,
                "trigger_reason": trigger_reason,
                "markdown_synced": sync_ok,
                "markdown_status": sync_status,
                "checkpoint_file": f"projects/{p_id}/checkpoint.md",
                "history_file": f"projects/{p_id}/checkpoints/checkpoint_v{version}.md"
            }

    def process_usage_telemetry(
        self,
        metrics: AgentUsageMetrics,
        state: Optional[CheckpointState] = None,
        project_id: Optional[str] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Evaluates incoming agent usage telemetry and automatically triggers
        proactive checkpointing when thresholds (70%, 80%, 90%, 95%) are crossed.
        """
        task_id = metrics.task_id or metrics.session_id or "default"
        agent_name = metrics.agent_name

        # Evaluate against policy thresholds
        trigger_reason = self.monitor.evaluate_metrics(metrics, force=force)

        if not trigger_reason:
            return {
                "triggered": False,
                "task_id": task_id,
                "usage_percentage": metrics.get_effective_usage_percentage(),
                "reason": "Threshold not reached or suppressed by cooldown/deduplication"
            }

        # Threshold 70% is lightweight preparation: alert agent / prepare cache
        if trigger_reason == TriggerReason.THRESHOLD_70_PREPARE:
            adapter = self.monitor.get_adapter(agent_name)
            if adapter:
                adapter.notify_agent(
                    warning_level="info",
                    message="Context window at 70%. Prepare lightweight checkpoint soon.",
                    task_id=task_id
                )
            return {
                "triggered": True,
                "task_id": task_id,
                "trigger_reason": trigger_reason.value,
                "action": "prepared_lightweight_warning",
                "usage_percentage": metrics.get_effective_usage_percentage()
            }

        # Threshold 90% or 95% triggers urgent notification
        adapter = self.monitor.get_adapter(agent_name)
        if adapter and trigger_reason in [TriggerReason.THRESHOLD_90_URGENT, TriggerReason.THRESHOLD_95_CRITICAL]:
            level = "urgent" if trigger_reason == TriggerReason.THRESHOLD_90_URGENT else "critical"
            msg = (
                f"Context window at {metrics.get_effective_usage_percentage()}%! "
                "Urgent checkpoint triggered. Avoid starting expensive operations."
            )
            adapter.notify_agent(warning_level=level, message=msg, task_id=task_id)

        # Trigger automatic checkpoint update
        res = self.execute_checkpoint(
            task_id=task_id,
            state=state,
            project_id=project_id,
            trigger_reason=trigger_reason.value,
            session_id=metrics.session_id,
            agent_name=agent_name,
            metrics=metrics
        )
        res["triggered"] = True
        res["usage_percentage"] = metrics.get_effective_usage_percentage()
        return res

