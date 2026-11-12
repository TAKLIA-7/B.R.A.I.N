import logging
from typing import Dict, Any, Optional
from core.adapters.postgres import PostgresAdapter
from core.handoff.checkpoint import CheckpointService
from core.handoff.context_builder import HandoverContextBuilder
from core.handoff.schemas import ResumeResponse

logger = logging.getLogger(__name__)

class ResumeService:
    """
    Coordinates task resumption for independent AI agents without raw conversation transcripts.
    Preserves completed/pending steps, decisions, bug investigations, and verified fixes.
    """

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        checkpoint_service: Optional[CheckpointService] = None,
        context_builder: Optional[HandoverContextBuilder] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.checkpoint_service = checkpoint_service or CheckpointService(postgres_adapter=self.pg)
        self.context_builder = context_builder or HandoverContextBuilder(postgres_adapter=self.pg)

    def resume_task(
        self,
        task_id: str,
        requesting_agent: str = "agent",
        token_budget: int = 4000
    ) -> ResumeResponse:
        """
        Resumes an unfinished task for a fresh agent.
        1. Loads canonical latest checkpoint from PostgreSQL.
        2. Consults JEV and HandoverContextBuilder to assemble actionable state.
        3. Enforces token budget and excludes all conversation transcripts.
        """
        cp = self.checkpoint_service.get_latest_checkpoint(task_id)
        if not cp:
            raise ValueError(f"Task '{task_id}' has no checkpoints or does not exist.")

        # Update task owner to requesting_agent
        self.checkpoint_service.update_task_owner(task_id, requesting_agent)

        handover_dict = self.context_builder.build_handover(
            task_id=task_id,
            checkpoint_data=cp,
            requesting_agent=requesting_agent,
            token_budget=token_budget
        )

        return ResumeResponse(**handover_dict)

# Alias for backwards compatibility
ResumeManager = ResumeService
