import os
import json
import logging
from typing import Dict, Any, List, Optional
from core.adapters.postgres import PostgresAdapter

logger = logging.getLogger(__name__)

class MarkdownProjectionGenerator:
    """
    Generates and updates human-readable Markdown documentation in bug_knowledge/.
    PostgreSQL is the source of truth. Projections are idempotent and can be safely regenerated.
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        postgres_adapter: Optional[PostgresAdapter] = None
    ):
        if base_dir is None:
            # Default to repo root / bug_knowledge
            current_dir = os.path.dirname(os.path.abspath(__file__))
            base_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "bug_knowledge"))
        self.base_dir = base_dir
        self.bugs_dir = os.path.join(self.base_dir, "bugs")
        self.fixes_dir = os.path.join(self.base_dir, "fixes")
        self.pg = postgres_adapter or PostgresAdapter()

        os.makedirs(self.bugs_dir, exist_ok=True)
        os.makedirs(self.fixes_dir, exist_ok=True)

    def generate_bug_markdown(self, bug_record: Dict[str, Any], attempts: List[Dict[str, Any]], fixes: List[Dict[str, Any]]) -> str:
        bug_id = bug_record["bug_id"]
        title = bug_record["title"]
        status = bug_record["status"]
        severity = bug_record.get("severity", "medium")
        reported_by = bug_record.get("reported_by", "unknown")
        first_seen = bug_record.get("first_seen", "")
        location = bug_record.get("location") or {}
        if isinstance(location, str):
            location = json.loads(location)
        symptom = bug_record.get("symptom") or "No symptoms recorded."
        root_cause = bug_record.get("root_cause") or "Root cause not yet determined."

        # Front matter
        lines = [
            "---",
            f"id: {bug_id}",
            f"title: \"{title}\"",
            f"status: {status}",
            f"severity: {severity}",
            f"reported_by: {reported_by}",
            f"first_seen: \"{first_seen}\"",
            f"files: {location.get('files', [])}",
            f"symbols: {location.get('symbols', [])}",
            "---",
            "",
            f"# {bug_id}: {title}",
            "",
            "## Symptoms and Reproduction",
            symptom,
            "",
            "## Root Cause",
            root_cause,
            "",
            "## Investigation Attempts"
        ]

        if attempts:
            for idx, att in enumerate(attempts, 1):
                outcome = att.get("outcome", "unknown").upper()
                agent = att.get("agent", "unknown")
                hypo = att.get("hypothesis", "")
                action = att.get("action", "")
                learned = att.get("learned") or ""
                lines.extend([
                    f"### Attempt {idx} [{outcome}] - {agent}",
                    f"- **Hypothesis**: {hypo}",
                    f"- **Action Taken**: {action}",
                    f"- **Learned / Next Steps**: {learned}",
                    ""
                ])
        else:
            lines.extend(["_No investigation attempts recorded yet._", ""])

        lines.extend([
            "## Resolution and Verification",
            f"- **Status**: `{status}`"
        ])

        if fixes:
            lines.extend(["", "### Related Fixes"])
            for fix in fixes:
                fid = fix["fix_id"]
                summary = fix.get("summary", "")
                fixed_by = fix.get("fixed_by", "unknown")
                ver = fix.get("verification") or {}
                if isinstance(ver, str):
                    ver = json.loads(ver)
                lines.append(f"- [{fid}](../fixes/{fid}.md) by `{fixed_by}`: {summary} (Result: `{ver.get('result', 'untested')}`)")
        else:
            lines.extend(["", "_No fixes recorded yet._"])

        return "\n".join(lines) + "\n"

    def generate_fix_markdown(self, fix_record: Dict[str, Any]) -> str:
        fix_id = fix_record["fix_id"]
        bug_id = fix_record["bug_id"]
        commit = fix_record.get("commit") or "N/A"
        fixed_by = fix_record.get("fixed_by", "unknown")
        created_at = fix_record.get("created_at", "")
        summary = fix_record.get("summary") or ""
        files_changed = fix_record.get("files_changed") or []
        if isinstance(files_changed, str):
            files_changed = json.loads(files_changed)
        verification = fix_record.get("verification") or {}
        if isinstance(verification, str):
            verification = json.loads(verification)

        lines = [
            "---",
            f"id: {fix_id}",
            f"bug_id: {bug_id}",
            f"commit: \"{commit}\"",
            f"fixed_by: {fixed_by}",
            f"created_at: \"{created_at}\"",
            f"files_changed: {files_changed}",
            "---",
            "",
            f"# Fix {fix_id} for [{bug_id}](../bugs/{bug_id}.md)",
            "",
            "## Summary",
            summary,
            "",
            "## Files Changed"
        ]
        for f in files_changed:
            lines.append(f"- `{f}`")
        if not files_changed:
            lines.append("_No files specified._")

        lines.extend([
            "",
            "## Verification Evidence",
            f"- **Tests Executed**: `{verification.get('tests', 'None')}`",
            f"- **Result**: `{verification.get('result', 'untested')}`",
            f"- **Run ID**: `{verification.get('run_id', 'N/A')}`",
            ""
        ])

        return "\n".join(lines) + "\n"

    def sync_all_projections(self) -> Dict[str, int]:
        """
        Idempotently regenerates Markdown documentation in bug_knowledge/ from PostgreSQL.
        Detects missing or outdated files and writes them.
        """
        bugs = self.pg.execute_query("SELECT * FROM bugs ORDER BY first_seen ASC;")
        bugs_synced = 0
        fixes_synced = 0

        for b in bugs:
            bid = b["bug_id"]
            attempts = self.pg.execute_query("SELECT * FROM attempts WHERE bug_id = %s ORDER BY created_at ASC;", (bid,))
            fixes = self.pg.execute_query("SELECT * FROM fixes WHERE bug_id = %s ORDER BY created_at ASC;", (bid,))
            
            # Write bug markdown
            bug_content = self.generate_bug_markdown(b, attempts, fixes)
            bug_path = os.path.join(self.bugs_dir, f"{bid}.md")
            with open(bug_path, "w", encoding="utf-8") as f:
                f.write(bug_content)
            bugs_synced += 1

            # Write fix markdown
            for fix in fixes:
                fid = fix["fix_id"]
                fix_content = self.generate_fix_markdown(fix)
                fix_path = os.path.join(self.fixes_dir, f"{fid}.md")
                with open(fix_path, "w", encoding="utf-8") as f:
                    f.write(fix_content)
                fixes_synced += 1

        # Update index.md
        index_path = os.path.join(self.base_dir, "index.md")
        index_lines = [
            "# Bug Knowledge Base Index",
            "",
            "This index is generated idempotently from authoritative PostgreSQL records.",
            "",
            "## Tracked Bugs",
            "| Bug ID | Title | Status | Severity | Reported By |",
            "|---|---|---|---|---|"
        ]
        for b in bugs:
            index_lines.append(f"| [{b['bug_id']}](./bugs/{b['bug_id']}.md) | {b['title']} | `{b['status']}` | `{b['severity']}` | {b.get('reported_by', 'agent')} |")

        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(index_lines) + "\n")

        return {"bugs_synced": bugs_synced, "fixes_synced": fixes_synced}

