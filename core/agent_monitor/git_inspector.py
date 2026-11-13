"""
core/agent_monitor/git_inspector.py
Safe inspection of Git working tree, status, branch, commit, and diff summaries.
"""
import subprocess
import os
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GitWorkingTreeState(BaseModel):
    branch: Optional[str] = None
    commit: Optional[str] = None
    files_created: List[str] = Field(default_factory=list)
    files_modified: List[str] = Field(default_factory=list)
    files_deleted: List[str] = Field(default_factory=list)
    uncommitted_changes_count: int = 0
    diff_summary: Optional[str] = None
    is_git_repo: bool = False


class GitInspector:
    """Safe Git inspector that never crashes if git is missing or repo is dirty."""

    def __init__(self, repo_path: Optional[str] = None):
        self.repo_path = repo_path or os.getcwd()

    def _run_git(self, args: List[str], timeout: int = 4) -> Optional[str]:
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if res.returncode == 0:
                return res.stdout.strip()
            return None
        except Exception as e:
            logger.debug(f"Git command failed (git {' '.join(args)}): {e}")
            return None

    def inspect(self) -> GitWorkingTreeState:
        """Inspects git repository working directory state."""
        # 1. Check if git repo
        is_repo = self._run_git(["rev-parse", "--is-inside-work-tree"]) == "true"
        if not is_repo:
            return GitWorkingTreeState(is_git_repo=False)

        # 2. Commit and branch
        commit = self._run_git(["rev-parse", "HEAD"])
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])

        # 3. Status porcelain
        status_out = self._run_git(["status", "--porcelain"]) or ""
        created: List[str] = []
        modified: List[str] = []
        deleted: List[str] = []

        for line in status_out.splitlines():
            line = line.strip()
            if not line:
                continue
            code = line[:2].strip()
            file_path = line[2:].strip()
            # Remove quotes if git quoted spaces
            if file_path.startswith('"') and file_path.endswith('"'):
                file_path = file_path[1:-1]

            if code in ["??", "A"]:
                created.append(file_path)
            elif code in ["M", "MM", "AM"]:
                modified.append(file_path)
            elif code in ["D"]:
                deleted.append(file_path)
            else:
                modified.append(file_path)

        uncommitted_count = len(created) + len(modified) + len(deleted)

        # 4. Compact diff stat (limit to 30 lines)
        diff_stat = self._run_git(["diff", "--stat"])
        if not diff_stat and status_out:
            diff_stat = f"{uncommitted_count} uncommitted file(s) changed."
        elif diff_stat:
            lines = diff_stat.splitlines()
            if len(lines) > 30:
                diff_stat = "\n".join(lines[:30]) + f"\n... ({len(lines) - 30} more files)"

        return GitWorkingTreeState(
            branch=branch,
            commit=commit,
            files_created=created,
            files_modified=modified,
            files_deleted=deleted,
            uncommitted_changes_count=uncommitted_count,
            diff_summary=diff_stat,
            is_git_repo=True
        )

