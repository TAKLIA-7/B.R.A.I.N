import os
import json
import logging
import re
from typing import Dict, Any, List, Optional
from core.config import settings
from core.adapters.postgres import PostgresAdapter

logger = logging.getLogger(__name__)

class ObsidianVaultExporter:
    """
    Exports canonical knowledge from PostgreSQL into an Obsidian Markdown vault.
    Generates structured human-facing notes with YAML frontmatter, internal [[wiki-links]],
    and categorical hashtags for Obsidian's Graph View.
    PostgreSQL remains the authoritative source of truth.
    """

    def __init__(
        self,
        vault_path: Optional[str] = "DEFAULT",
        postgres_adapter: Optional[PostgresAdapter] = None
    ):
        if vault_path == "DEFAULT":
            self.vault_path = os.path.abspath(settings.OBSIDIAN_VAULT_PATH) if settings.OBSIDIAN_VAULT_PATH else None
        elif vault_path:
            self.vault_path = os.path.abspath(vault_path)
        else:
            self.vault_path = None

        self.pg = postgres_adapter

    def _ensure_dirs(self):
        if not self.vault_path:
            return
        os.makedirs(self.vault_path, exist_ok=True)
        os.makedirs(os.path.join(self.vault_path, "Memories"), exist_ok=True)
        os.makedirs(os.path.join(self.vault_path, "Projects"), exist_ok=True)
        os.makedirs(os.path.join(self.vault_path, "Tasks"), exist_ok=True)
        os.makedirs(os.path.join(self.vault_path, "Bugs"), exist_ok=True)
        os.makedirs(os.path.join(self.vault_path, "Fixes"), exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        # Remove characters forbidden on Windows/Unix filesystems: < > : " / \ | ? *
        clean = re.sub(r'[<>:"/\\|?*]', '_', str(name))
        return clean.strip() or "unnamed"

    def format_memory_note(self, memory: Dict[str, Any]) -> str:
        mid = memory.get("memory_id", "")
        mtype = memory.get("memory_type", "fact")
        title = memory.get("title") or memory.get("metadata", {}).get("title") or f"Memory {mid}"
        epistemic = memory.get("epistemic_state", "asserted")
        trust = memory.get("trust_score", 0.5)
        project = memory.get("project") or memory.get("metadata", {}).get("project") or "General"
        tags = memory.get("tags") or memory.get("metadata", {}).get("tags") or []
        content = memory.get("content", "")
        source_id = memory.get("source_id", "unknown")

        tag_strs = [f"#{mtype}"]
        for t in tags:
            tag_strs.append(f"#{t}")

        lines = [
            "---",
            f"id: {mid}",
            f"type: {mtype}",
            f"epistemic_state: {epistemic}",
            f"trust_score: {trust}",
            f"project: \"{project}\"",
            f"source_id: \"{source_id}\"",
            f"tags: {json.dumps(tags)}",
            "---",
            "",
            f"# {title}",
            "",
            f"**Project**: [[Projects/{project}|{project}]]",
            f"**Epistemic State**: `{epistemic}` | **Trust**: `{trust}`",
            f"**Tags**: {' '.join(tag_strs)}",
            "",
            "## Content",
            content,
            "",
            "## Provenance",
            f"- Canonical Source: `{source_id}`",
            f"- Memory ID: `{mid}`"
        ]
        return "\n".join(lines)

    def format_bug_note(self, bug: Dict[str, Any]) -> str:
        bid = bug.get("bug_id") or ""
        title = bug.get("title") or ""
        status = bug.get("status") or "open"
        severity = bug.get("severity") or "medium"
        symptom = bug.get("symptom") or "No symptoms documented."
        root_cause = bug.get("root_cause") or "Root cause under investigation."
        rel_fix = bug.get("related_fix_id") or ""
        rel_task = bug.get("related_task_id") or ""
        location = bug.get("location") or {}
        if isinstance(location, str):
            try:
                location = json.loads(location)
            except Exception:
                location = {}

        project = bug.get("project") or location.get("project") or "General"

        lines = [
            "---",
            f"id: {bid}",
            f"title: \"{title}\"",
            f"status: {status}",
            f"severity: {severity}",
            f"project: \"{project}\"",
            f"related_fix_id: \"{rel_fix}\"",
            f"related_task_id: \"{rel_task}\"",
            "---",
            "",
            f"# {bid}: {title}",
            "",
            f"**Project**: [[Projects/{project}|{project}]]",
            f"**Status**: `{status}` | **Severity**: `{severity}`",
            f"**Tags**: #bug #{severity} #bug/{status}",
            "",
            "## Symptoms and Reproduction",
            symptom,
            "",
            "## Root Cause",
            root_cause,
            "",
            "## Investigation & Resolution"
        ]

        if rel_fix:
            lines.append(f"- Verified Fix: [[Fixes/{rel_fix}|{rel_fix}]]")
        else:
            lines.append("- _No verified fix recorded yet._")

        if rel_task:
            lines.append(f"- Associated Task: [[Tasks/{rel_task}|{rel_task}]]")

        return "\n".join(lines)

    def format_fix_note(self, fix: Dict[str, Any]) -> str:
        fid = fix.get("fix_id") or ""
        bid = fix.get("bug_id") or ""
        summary = fix.get("summary") or "No summary recorded."
        fixed_by = fix.get("fixed_by") or "unknown"
        ver_result = fix.get("verification_result") or ""
        ver_output = fix.get("verification_output") or ""
        
        # In case verification is passed as a dict
        ver = fix.get("verification")
        if isinstance(ver, dict):
            ver_result = ver.get("result", ver_result)
            ver_output = ver.get("output", ver_output)
        elif isinstance(ver, str):
            try:
                vdict = json.loads(ver)
                ver_result = vdict.get("result", ver_result)
                ver_output = vdict.get("output", ver_output)
            except Exception:
                pass

        status_tag = "#fix/verified" if ver_result == "passed" else "#fix/unverified"

        lines = [
            "---",
            f"id: {fid}",
            f"bug_id: \"{bid}\"",
            f"fixed_by: \"{fixed_by}\"",
            f"verification_result: \"{ver_result}\"",
            "---",
            "",
            f"# Fix {fid}",
            "",
            f"**Resolved Bug**: [[Bugs/{bid}|{bid}]]",
            f"**Fixed by**: `{fixed_by}`",
            f"**Tags**: #fix {status_tag}",
            "",
            "## Summary",
            summary,
            "",
            "## Verification Evidence",
            f"- **Result**: `{ver_result}`",
            f"- **Proof Output**:",
            "```text",
            ver_output or "No output logged.",
            "```"
        ]
        return "\n".join(lines)

    def format_task_note(self, task: Dict[str, Any]) -> str:
        tid = task.get("task_id") or ""
        desc = task.get("description") or "No description."
        status = task.get("status") or "pending"
        metadata = task.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        project = task.get("project") or metadata.get("project") or "General"

        lines = [
            "---",
            f"id: {tid}",
            f"status: {status}",
            f"project: \"{project}\"",
            "---",
            "",
            f"# Task {tid}",
            "",
            f"**Project**: [[Projects/{project}|{project}]]",
            f"**Status**: `{status}`",
            f"**Tags**: #task #task/{status}",
            "",
            "## Description",
            desc
        ]
        return "\n".join(lines)

    def format_project_note(self, project_name: str, items: Dict[str, List[Any]]) -> str:
        lines = [
            "---",
            f"project: \"{project_name}\"",
            "type: project",
            "---",
            "",
            f"# Project: {project_name}",
            "",
            f"Hub note for **{project_name}** connecting memories, architectural decisions, tasks, and bugs.",
            "",
            "## Associated Tasks"
        ]
        tasks = items.get("tasks", [])
        if tasks:
            for t in tasks:
                tid = t.get("task_id") or "unknown"
                desc = t.get("description") or ""
                status = t.get("status") or ""
                lines.append(f"- [[Tasks/{tid}|{tid}]]: {desc} (`{status}`)")
        else:
            lines.append("- _No tasks recorded for this project._")

        lines.extend(["", "## Key Memories & Decisions"])
        memories = items.get("memories", [])
        if memories:
            for m in memories:
                mid = m.get("memory_id") or "unknown"
                mtitle = m.get("title") or m.get("metadata", {}).get("title") or mid
                mtype = m.get("memory_type") or "fact"
                lines.append(f"- [[Memories/{mid}|{mtitle}]] (`{mtype}`)")
        else:
            lines.append("- _No memories recorded for this project._")

        lines.extend(["", "## Defects & Bug History"])
        bugs = items.get("bugs", [])
        if bugs:
            for b in bugs:
                bid = b.get("bug_id") or "unknown"
                btitle = b.get("title") or ""
                bstatus = b.get("status") or ""
                lines.append(f"- [[Bugs/{bid}|{bid}]]: {btitle} (`{bstatus}`)")
        else:
            lines.append("- _No bugs recorded for this project._")

        return "\n".join(lines)

    def format_home_note(self, stats: Dict[str, int]) -> str:
        return f"""---
title: Knowledge Brain Vault Home
tags: #dashboard #index
---

# Knowledge Brain Dashboard

Welcome to the **Knowledge Brain** Obsidian Projection Vault.
This vault is an idempotent, human-readable view of the canonical persistent knowledge stored in PostgreSQL.

## Vault Statistics
- **Memories / Decisions**: {stats.get('memories', 0)}
- **Projects**: {stats.get('projects', 0)}
- **Tasks**: {stats.get('tasks', 0)}
- **Tracked Bugs**: {stats.get('bugs', 0)}
- **Verified Fixes**: {stats.get('fixes', 0)}

## Main Hubs
- [[Projects/General|Projects Hub]]
- Browse notes by tag in the Obsidian tags pane (`#decision`, `#bug`, `#verified`, `#task`).
- Open **Graph View** (`Ctrl+G` / `Cmd+G`) in Obsidian to inspect knowledge clusters and relationship links.
"""

    def export_all_records(
        self,
        memories: List[Dict[str, Any]],
        bugs: List[Dict[str, Any]],
        fixes: List[Dict[str, Any]],
        tasks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Exports provided memory, bug, fix, and task records into the vault.
        Idempotent: notes are overwritten with identical normalized markdown.
        """
        if not self.vault_path:
            return {
                "status": "skipped",
                "message": "Vault path is not configured",
                "exported_files": 0
            }

        try:
            self._ensure_dirs()
            file_count = 0
            projects_map: Dict[str, Dict[str, List[Any]]] = {}

            # 1. Export Memories
            for m in memories:
                mid = self._sanitize_filename(m.get("memory_id", "unknown"))
                proj = m.get("project") or m.get("metadata", {}).get("project") or "General"
                projects_map.setdefault(proj, {"memories": [], "tasks": [], "bugs": []})["memories"].append(m)

                file_path = os.path.join(self.vault_path, "Memories", f"{mid}.md")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.format_memory_note(m))
                file_count += 1

            # 2. Export Bugs
            for b in bugs:
                bid = self._sanitize_filename(b.get("bug_id", "unknown"))
                loc = b.get("location") or {}
                if isinstance(loc, str):
                    try:
                        loc = json.loads(loc)
                    except Exception:
                        loc = {}
                proj = b.get("project") or loc.get("project") or "General"
                projects_map.setdefault(proj, {"memories": [], "tasks": [], "bugs": []})["bugs"].append(b)

                file_path = os.path.join(self.vault_path, "Bugs", f"{bid}.md")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.format_bug_note(b))
                file_count += 1

            # 3. Export Fixes
            for fix in fixes:
                fid = self._sanitize_filename(fix.get("fix_id", "unknown"))
                file_path = os.path.join(self.vault_path, "Fixes", f"{fid}.md")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.format_fix_note(fix))
                file_count += 1

            # 4. Export Tasks
            for t in tasks:
                tid = self._sanitize_filename(t.get("task_id", "unknown"))
                meta = t.get("metadata") or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                proj = t.get("project") or meta.get("project") or "General"
                projects_map.setdefault(proj, {"memories": [], "tasks": [], "bugs": []})["tasks"].append(t)

                file_path = os.path.join(self.vault_path, "Tasks", f"{tid}.md")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.format_task_note(t))
                file_count += 1

            # 5. Export Projects
            for proj_name, items in projects_map.items():
                pfilename = self._sanitize_filename(proj_name)
                file_path = os.path.join(self.vault_path, "Projects", f"{pfilename}.md")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.format_project_note(proj_name, items))
                file_count += 1

            # 6. Export Home Dashboard
            home_path = os.path.join(self.vault_path, "Home.md")
            stats = {
                "memories": len(memories),
                "bugs": len(bugs),
                "fixes": len(fixes),
                "tasks": len(tasks),
                "projects": len(projects_map)
            }
            with open(home_path, "w", encoding="utf-8") as f:
                f.write(self.format_home_note(stats))
            file_count += 1

            return {
                "status": "success",
                "vault_path": self.vault_path,
                "exported_files": file_count,
                "counts": stats
            }
        except Exception as e:
            logger.error(f"Error exporting Obsidian vault: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "exported_files": 0
            }

    def sync_from_postgres(self) -> Dict[str, Any]:
        """
        Loads all active records from PostgreSQL canonical tables and exports them
        into the configured Obsidian vault.
        """
        if not self.vault_path:
            return {
                "status": "skipped",
                "message": "Vault path is not configured",
                "exported_files": 0
            }

        pg = self.pg or PostgresAdapter()

        try:
            with pg.get_connection() as conn:
                with conn.cursor() as cur:
                    # 1. Fetch active memories
                    cur.execute("""
                        SELECT m.id, m.type, m.text, m.epistemic_state,
                               COALESCE(s.trust_level, 0.50) as trust_level,
                               m.subject, m.predicate, m.object, m.source_id
                        FROM memories m
                        LEFT JOIN sources s ON m.source_id = s.id
                        WHERE m.status = 'active'
                        ORDER BY m.created_at DESC;
                    """)
                    memories = []
                    for row in cur.fetchall():
                        mid = str(row[0])
                        mtype = row[1]
                        mtext = row[2]
                        epistemic = row[3]
                        trust = float(row[4]) if row[4] is not None else 0.50
                        subject = row[5] or ""
                        source_id = str(row[8]) if row[8] else "unknown"

                        memories.append({
                            "memory_id": mid,
                            "source_id": source_id,
                            "memory_type": mtype,
                            "content": mtext,
                            "epistemic_state": epistemic,
                            "trust_score": trust,
                            "title": subject or f"{mtype.capitalize()}: {mid[:8]}",
                            "project": subject if subject else "General"
                        })

                    # 2. Fetch bugs with linked fixes if present
                    cur.execute("""
                        SELECT b.bug_id, b.title, b.status, b.severity, b.symptom, b.root_cause, b.location,
                               f.fix_id as related_fix_id
                        FROM bugs b
                        LEFT JOIN fixes f ON b.bug_id = f.bug_id
                        ORDER BY b.first_seen DESC;
                    """)
                    bugs = []
                    for row in cur.fetchall():
                        bugs.append({
                            "bug_id": row[0],
                            "title": row[1],
                            "status": row[2],
                            "severity": row[3],
                            "symptom": row[4],
                            "root_cause": row[5],
                            "location": row[6],
                            "related_fix_id": row[7]
                        })

                    # 3. Fetch fixes
                    cur.execute("""
                        SELECT fix_id, bug_id, summary, fixed_by, verification
                        FROM fixes
                        ORDER BY created_at DESC;
                    """)
                    fixes = []
                    for row in cur.fetchall():
                        fixes.append({
                            "fix_id": row[0],
                            "bug_id": row[1],
                            "summary": row[2],
                            "fixed_by": row[3],
                            "verification": row[4]
                        })

                    # 4. Fetch tasks
                    cur.execute("""
                        SELECT id, goal, created_by
                        FROM tasks
                        ORDER BY created_at DESC;
                    """)
                    tasks = []
                    for row in cur.fetchall():
                        tasks.append({
                            "task_id": row[0],
                            "description": row[1],
                            "status": "active",
                            "project": "General"
                        })

            return self.export_all_records(
                memories=memories,
                bugs=bugs,
                fixes=fixes,
                tasks=tasks
            )
        except Exception as e:
            logger.error(f"PostgreSQL read error during Obsidian sync: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "exported_files": 0
            }
