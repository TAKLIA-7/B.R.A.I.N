"""
core/agent_monitor/checkpoint_generator.py
Generates the authoritative Markdown projection for project `checkpoint.md`.
Enforces sections A through H as specified in Knowledge Brain proactive checkpointing architecture.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from core.handoff.schemas import CheckpointState
from core.agent_monitor.git_inspector import GitWorkingTreeState


class CheckpointMarkdownGenerator:
    """
    Constructs high-fidelity, human-readable and agent-resumable `checkpoint.md` documents.
    """

    @staticmethod
    def generate_checkpoint_md(
        state: CheckpointState,
        project_id: str,
        project_name: Optional[str] = None,
        checkpoint_version: int = 1,
        trigger_reason: str = "manual",
        session_id: Optional[str] = None,
        git_state: Optional[GitWorkingTreeState] = None,
        bugs: Optional[List[Dict[str, Any]]] = None,
        fixes: Optional[List[Dict[str, Any]]] = None,
        extra_context: Optional[Dict[str, Any]] = None
    ) -> str:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        p_name = project_name or project_id

        # 1. Determine steps state
        completed_steps = [s for s in state.steps if str(s.status).lower() in ["done", "stepstatus.done"]]
        in_progress_steps = [s for s in state.steps if str(s.status).lower() in ["in_progress", "stepstatus.in_progress"]]
        pending_steps = [s for s in state.steps if str(s.status).lower() in ["pending", "stepstatus.pending"]]

        last_completed = completed_steps[-1].state if completed_steps else "None yet"
        current_work = in_progress_steps[0].state if in_progress_steps else (pending_steps[0].state if pending_steps else "Task completed")

        # 2. Git details
        branch = state.git_branch or (git_state.branch if git_state else "unknown")
        commit = state.git_commit or (git_state.commit if git_state else "unknown")
        created_files = git_state.files_created if git_state else []
        modified_files = git_state.files_modified if git_state else []
        deleted_files = git_state.files_deleted if git_state else []
        diff_summary = git_state.diff_summary if git_state else None
        uncommitted_count = git_state.uncommitted_changes_count if git_state else 0

        # Build Markdown
        md: List[str] = []

        # Header
        md.append(f"# Project Checkpoint: {p_name} (`{project_id}`)")
        md.append("")
        md.append(f"> **Checkpoint Version:** `v{checkpoint_version}`  ")
        md.append(f"> **Captured At:** {now_str}  ")
        md.append(f"> **Trigger Reason:** `{trigger_reason}`  ")
        md.append(f"> **Canonical Source of Truth:** PostgreSQL (`tasks` / `checkpoints` tables)  ")
        md.append("")
        md.append("---")
        md.append("")

        # Section A: Current Task
        md.append("## A. Current Task")
        md.append(f"- **Task ID:** `{state.task_id}`")
        md.append(f"- **Project ID / Name:** `{project_id}` / {p_name}")
        md.append(f"- **Objective:** {state.goal}")
        md.append(f"- **Active Agent:** `{state.written_by}`")
        md.append(f"- **Session ID:** `{session_id or 'not-specified'}`")
        md.append("")

        # Section B: Recent Changes
        md.append("## B. Recent Changes")
        if created_files:
            md.append("### Files Created")
            for f in created_files[:15]:
                md.append(f"- `+` `{f}`")
        if modified_files:
            md.append("### Files Modified")
            for f in modified_files[:20]:
                md.append(f"- `*` `{f}`")
        if deleted_files:
            md.append("### Files Deleted")
            for f in deleted_files[:15]:
                md.append(f"- `-` `{f}`")
        if not (created_files or modified_files or deleted_files):
            if state.project_files:
                md.append("### Project Files Touched")
                for pf in state.project_files:
                    md.append(f"- `{pf}`")
            else:
                md.append("- No uncommitted file modifications detected in working tree.")

        if diff_summary:
            md.append("")
            md.append("```text")
            md.append(diff_summary.strip())
            md.append("```")
        md.append("")

        # Section C: Completed Work
        md.append("## C. Completed Work")
        if completed_steps:
            for s in completed_steps:
                evidence_text = f" (Evidence: {', '.join(s.evidence)})" if s.evidence else ""
                md.append(f"- [x] **{s.id}:** {s.state}{evidence_text}")
        else:
            md.append("- No steps marked as completed in this task yet.")

        if state.test_results:
            md.append("")
            md.append("### Tests Executed")
            for t in state.test_results:
                md.append(f"- {t}")

        if fixes:
            md.append("")
            md.append("### Verified Fixes Applied")
            for fix in fixes:
                md.append(f"- **{fix.get('fix_id', 'FIX')}:** {fix.get('summary', 'Resolved issue')}")
        md.append("")

        # Section D: Current Working State
        md.append("## D. Current Working State")
        md.append(f"- **Current In-Progress Focus:** {current_work}")
        md.append(f"- **Last Completed Step:** {last_completed}")
        md.append(f"- **Git Branch:** `{branch}`")
        md.append(f"- **Latest Commit:** `{commit}`")
        md.append(f"- **Uncommitted Changes Count:** {uncommitted_count}")
        if in_progress_steps:
            md.append("")
            md.append("### In-Progress Step Details")
            for step in in_progress_steps:
                md.append(f"- `[ ]` **{step.id}:** {step.state}")
        md.append("")

        # Section E: Decisions and Reasoning
        md.append("## E. Decisions and Reasoning")
        if state.decisions:
            for d in state.decisions:
                md.append(f"- **Decision:** {d.what}")
                md.append(f"  - **Why:** {d.why}")
                md.append(f"  - **Source:** `{d.source}`")
        else:
            md.append("- No explicit architectural decisions recorded for this checkpoint.")

        if state.rejected:
            md.append("")
            md.append("### Alternatives Considered and Rejected")
            for r in state.rejected:
                md.append(f"- **Rejected:** {r.option} (Reason: {r.reason})")
        md.append("")

        # Section F: Known Problems
        md.append("## F. Known Problems")
        if bugs:
            for b in bugs:
                md.append(f"- **Bug `{b.get('bug_id')}` [{b.get('severity', 'medium')}]:** {b.get('title')}")
                if b.get("symptom"):
                    md.append(f"  - *Symptom:* {b.get('symptom')}")
                if b.get("root_cause"):
                    md.append(f"  - *Root Cause:* {b.get('root_cause')}")
        elif state.open_questions:
            md.append("### Open Questions & Unresolved Issues")
            for q in state.open_questions:
                md.append(f"- {q}")
        else:
            md.append("- No active blockers or unresolved defects recorded.")
        md.append("")

        # Section G: Next Steps
        md.append("## G. Next Steps")
        if pending_steps:
            for idx, p in enumerate(pending_steps, 1):
                md.append(f"{idx}. **{p.id}:** {p.state}")
        else:
            md.append("1. Verify final test pass and close task.")

        if state.open_questions and bugs:
            md.append("")
            md.append("### Questions Needing Resolution")
            for q in state.open_questions:
                md.append(f"- {q}")
        md.append("")

        # Section H: Resumption Instructions
        md.append("## H. Resumption Instructions")
        md.append("To resume this task without needing conversational transcripts:")
        md.append(f"1. **Task Identification:** Call `task_resume(task_id='{state.task_id}')` to retrieve active state and defect linkages.")
        md.append(f"2. **Working Branch:** Ensure your Git workspace is checked out on branch `{branch}`.")
        md.append(f"3. **Immediate Step:** Begin execution on `{current_work}`.")
        md.append(f"4. **Decisions Context:** Review Section E above to avoid repeating rejected architectural approaches.")
        md.append("5. **Continuous Checkpointing:** Invoke `task_checkpoint` after every completed milestone before context window exhaustion.")
        md.append("")

        return "\n".join(md)

