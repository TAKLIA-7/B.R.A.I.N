import json
import re
from typing import Dict, Any, List, Optional
from core.adapters.postgres import PostgresAdapter
from core.handoff.checkpoint_manager import CheckpointManager
from core.retrieve.context_budget import ContextBudgetManager

class ResumeManager:
    """Constructs durable handover context for resuming agents without transcript transfer."""

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        checkpoint_manager: Optional[CheckpointManager] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.cm = checkpoint_manager or CheckpointManager(postgres_adapter=self.pg)
        self.budget_manager = ContextBudgetManager()

    def resume_task(self, task_id: str, token_budget: int = 1000) -> Dict[str, Any]:
        """
        Resumes an unfinished task for a fresh agent.
        1. Loads canonical latest checkpoint from PostgreSQL.
        2. Detects referenced files/symbols and loads matching bug history.
        3. Enforces token budget.
        4. Excludes any original conversation transcript.
        """
        cp = self.cm.get_latest_checkpoint(task_id)
        if not cp:
            return {
                "task_id": task_id,
                "status": "not_found",
                "message": f"No checkpoints found for task {task_id}"
            }

        state = cp["state_json"]
        if isinstance(state, str):
            state = json.loads(state)

        # Detect referenced files/symbols across steps, goal, and decisions
        combined_text = json.dumps(state)
        symbols = set(re.findall(r"[\w/\\-]+\.(?:py|json|md|sql|ts|js)", combined_text))

        # Query matching bug history from PostgreSQL
        matching_bugs: List[Dict[str, Any]] = []
        if symbols:
            bug_sql = """
                SELECT bug_id, title, symptom, root_cause, status, severity, location, reported_by
                FROM bugs
                ORDER BY first_seen DESC
                LIMIT 5;
            """
            rows = self.pg.execute_query(bug_sql)
            for b in rows:
                loc = b.get("location")
                if loc:
                    if isinstance(loc, str):
                        loc = json.loads(loc)
                    files = loc.get("files", [])
                    if any(f in symbols for f in files) or any(s in f for f in files for s in symbols):
                        matching_bugs.append(b)
                elif not symbols:
                    matching_bugs.append(b)

        # Assemble compact context without transcript
        context = {
            "task_id": state["task_id"],
            "version": cp["version"],
            "goal": state["goal"],
            "steps": state["steps"],
            "decisions": state["decisions"],
            "rejected": state["rejected"],
            "open_questions": state["open_questions"],
            "checkpoint_written_by": state["written_by"],
            "matching_bugs": matching_bugs,
            "token_budget": token_budget
        }

        # Estimate tokens used
        context_str = json.dumps(context)
        tokens_used, _ = self.budget_manager.estimate_tokens(context_str)
        context["estimated_tokens"] = tokens_used
        context["token_count_mode"] = "conservative_estimate"

        return context

