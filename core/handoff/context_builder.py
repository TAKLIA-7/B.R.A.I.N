import json
import logging
import re
from typing import Dict, Any, List, Optional
from core.adapters.postgres import PostgresAdapter
from core.jev.engine import JEVDecisionEngine
from core.retrieve.context_budget import ContextBudgetManager

logger = logging.getLogger(__name__)

class HandoverContextBuilder:
    """
    Constructs compact, actionable handover packages for resuming agents without transcripts.
    Uses JEV to prioritize critical decisions, bugs, and fixes within the token budget.
    """

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        jev_engine: Optional[JEVDecisionEngine] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.jev = jev_engine or JEVDecisionEngine(postgres_adapter=self.pg)
        self.budget_manager = ContextBudgetManager()

    def build_handover(
        self,
        task_id: str,
        checkpoint_data: Dict[str, Any],
        requesting_agent: str = "agent",
        token_budget: int = 4000
    ) -> Dict[str, Any]:
        state = checkpoint_data["state_json"]
        if isinstance(state, str):
            state = json.loads(state)

        # 1. Separate completed vs pending steps
        completed_steps = []
        pending_steps = []
        for step in state.get("steps", []):
            desc = step.get("state") or step.get("description") or step.get("id")
            if step.get("status") == "done":
                completed_steps.append(desc)
            else:
                pending_steps.append(desc)

        # 2. Extract decisions & rejected approaches
        decisions_list = []
        for d in state.get("decisions", []):
            if isinstance(d, dict):
                decisions_list.append(f"{d.get('what', '')}: {d.get('why', '')}")
            else:
                decisions_list.append(str(d))

        rejected_list = []
        for r in state.get("rejected", []):
            if isinstance(r, dict):
                rejected_list.append(f"{r.get('option', '')}: {r.get('reason', '')}")
            else:
                rejected_list.append(str(r))

        # 3. Detect symbols and files from project_files and steps
        symbols = set(state.get("project_files", []))
        combined_text = json.dumps(state)
        symbols.update(re.findall(r"[\w/\\-]+\.(?:py|json|md|sql|ts|js)", combined_text))

        # 4. Query matching bug history and verified fixes from PostgreSQL
        related_bugs: List[Dict[str, Any]] = []
        verified_fixes: List[Dict[str, Any]] = []

        try:
            with self.pg.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT bug_id, title, symptom, root_cause, status, severity, location, reported_by
                        FROM bugs
                        ORDER BY first_seen DESC LIMIT 10;
                    """)
                    for b in cur.fetchall():
                        bid, title, symptom, root_cause, bstatus, severity, loc, reported_by = b
                        loc_files = []
                        if loc:
                            if isinstance(loc, str):
                                try:
                                    loc = json.loads(loc)
                                except Exception:
                                    loc = {}
                            loc_files = loc.get("files", [])

                        # Match by symbols or if symbol list is empty
                        if not symbols or any(f in symbols for f in loc_files) or any(s in f for f in loc_files for s in symbols):
                            related_bugs.append({
                                "bug_id": bid,
                                "title": title,
                                "symptom": symptom,
                                "root_cause": root_cause,
                                "status": bstatus,
                                "severity": severity,
                                "reported_by": reported_by
                            })

                    # Verified fixes
                    cur.execute("""
                        SELECT fix_id, bug_id, summary, fixed_by, verification
                        FROM fixes
                        ORDER BY created_at DESC LIMIT 10;
                    """)
                    for f in cur.fetchall():
                        fid, f_bid, summary, fixed_by, ver = f
                        if isinstance(ver, str):
                            try:
                                ver = json.loads(ver)
                            except Exception:
                                ver = {}
                        if any(b["bug_id"] == f_bid for b in related_bugs):
                            verified_fixes.append({
                                "fix_id": fid,
                                "bug_id": f_bid,
                                "summary": summary,
                                "fixed_by": fixed_by,
                                "verification": ver
                            })
        except Exception as e:
            logger.warning(f"Error querying bugs/fixes for handover: {e}")

        # 5. Consult JEV Decision Engine for intelligent selection
        jev_decision, _ = self.jev.decide_handover(task_id=task_id, token_budget=token_budget)

        # Merge open questions
        all_open_questions = list(set(state.get("open_questions", []) + jev_decision.unresolved_questions))

        # 6. Format compact text context for the agent
        task_info = self.pg.execute_query(
            "SELECT target_requirement_id, target_requirement_version, is_stale FROM tasks WHERE id = %s;",
            (task_id,)
        )
        req_id = None
        target_req_ver = None
        is_stale = False
        staleness_warning = None
        if task_info:
            req_id = task_info[0].get("target_requirement_id")
            target_req_ver = task_info[0].get("target_requirement_version")
            is_stale = task_info[0].get("is_stale", False)
            if req_id:
                req_rows = self.pg.execute_query(
                    "SELECT current_version FROM requirements WHERE req_id = %s;", (req_id,)
                )
                if req_rows and target_req_ver and req_rows[0]["current_version"] > target_req_ver:
                    is_stale = True
                    staleness_warning = f"Requirement {req_id} was upgraded to v{req_rows[0]['current_version']} (Task was built against v{target_req_ver})."

        summary_lines = [
            f"# Handover Package: Task {task_id}",
            f"**Goal**: {state.get('goal')}",
            f"**Checkpoint Version**: {checkpoint_data.get('version')}",
            f"**Previous Agent**: {checkpoint_data.get('written_by')}",
            f"**Requesting Agent**: {requesting_agent}",
            f"**Git Commit**: {checkpoint_data.get('git_commit') or 'Uncommitted working tree'}",
            f"**Git Branch**: {checkpoint_data.get('git_branch') or 'unknown'}",
        ]
        if req_id:
            summary_lines.append(f"**Target Requirement**: {req_id} (Target v{target_req_ver or 1})")
        if is_stale:
            summary_lines.append(f"> [!WARNING] Task Context is STALE! {staleness_warning or 'Upstream requirement has changed.'}")

        summary_lines.append("")
        summary_lines.append("## Completed Steps")
        for s in completed_steps:
            summary_lines.append(f"- [x] {s}")

        summary_lines.extend(["", "## Pending Steps"])
        for s in pending_steps:
            summary_lines.append(f"- [ ] {s}")

        summary_lines.extend(["", "## Architectural Decisions"])
        for d in decisions_list:
            summary_lines.append(f"- {d}")

        if rejected_list:
            summary_lines.extend(["", "## Rejected Approaches"])
            for r in rejected_list:
                summary_lines.append(f"- {r}")

        if related_bugs:
            summary_lines.extend(["", "## Relevant Bug Investigations"])
            for b in related_bugs:
                summary_lines.append(f"- **{b['bug_id']}**: {b['title']} (Status: `{b['status']}`)")

        if verified_fixes:
            summary_lines.extend(["", "## Verified Fixes"])
            for f in verified_fixes:
                summary_lines.append(f"- **{f['fix_id']}** for `{f['bug_id']}`: {f['summary']}")

        if all_open_questions:
            summary_lines.extend(["", "## Unresolved Questions"])
            for q in all_open_questions:
                summary_lines.append(f"- ? {q}")

        handover_text = "\n".join(summary_lines)

        return {
            "task_id": task_id,
            "goal": state.get("goal", ""),
            "checkpoint_version": checkpoint_data["version"],
            "latest_version": checkpoint_data["version"],
            "version": checkpoint_data["version"],
            "previous_agent": checkpoint_data["written_by"],
            "checkpoint_written_by": checkpoint_data["written_by"],
            "requesting_agent": requesting_agent,
            "completed_steps": completed_steps,
            "pending_steps": pending_steps,
            "steps": state.get("steps", []),
            "decisions": decisions_list,
            "rejected_approaches": rejected_list,
            "rejected": state.get("rejected", []),
            "related_bugs": related_bugs,
            "matching_bugs": related_bugs,
            "verified_fixes": verified_fixes,
            "open_questions": all_open_questions,
            "handover_context": handover_text,
            "token_budget": min(token_budget, jev_decision.token_budget),
            "is_stale": is_stale,
            "target_requirement_id": req_id,
            "target_requirement_version": target_req_ver,
            "staleness_warning": staleness_warning
        }
