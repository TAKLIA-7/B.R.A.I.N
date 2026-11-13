"""
core/agent_monitor/antigravity_adapter.py
Adapter for Google Antigravity agent lifecycle, transcript inspection, and context monitoring.
"""
import logging
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from core.agent_monitor.base_adapter import BaseAgentAdapter, AgentUsageMetrics

logger = logging.getLogger(__name__)

# Standard context window capacities for models commonly used in Antigravity
ANTIGRAVITY_MODEL_CAPACITIES: Dict[str, int] = {
    "gemini-1.5-pro": 2097152,
    "gemini-1.5-flash": 1048576,
    "gemini-2.0-flash": 1048576,
    "gemini-2.5-flash": 1048576,
    "gemini-3.8-flash": 1048576,
    "claude-3-5-sonnet": 200000,
    "claude-3-7-sonnet": 200000,
    "claude-sonnet-4-6": 200000,
    "claude-opus-4": 200000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
}


class AntigravityAdapter(BaseAgentAdapter):
    """
    Adapter for Google Antigravity.
    Integrates with Antigravity AppData transcripts, session logs, and MCP notification events.
    """

    def __init__(
        self,
        app_data_dir: Optional[str] = None,
        default_model: str = "gemini-3.8-flash"
    ):
        super().__init__(agent_name="antigravity")
        self.app_data_dir = app_data_dir or os.environ.get(
            "ANTIGRAVITY_APP_DATA_DIR",
            os.path.expanduser("~/.gemini/antigravity")
        )
        self.default_model = default_model
        self.injected_metrics: Dict[str, AgentUsageMetrics] = {}
        self.notifications: List[Dict[str, Any]] = []

    def set_injected_metrics(self, session_or_task_id: str, metrics: AgentUsageMetrics) -> None:
        """Allow host or lifecycle hooks to directly register observed usage."""
        self.injected_metrics[session_or_task_id] = metrics

    def lookup_model_capacity(self, model_name: Optional[str]) -> Optional[int]:
        """Look up known context capacity for model without guessing unknown models."""
        if not model_name:
            return None
        norm = model_name.lower().replace(" ", "-").replace("_", "-")
        for key, cap in ANTIGRAVITY_MODEL_CAPACITIES.items():
            if key in norm or norm in key:
                return cap
        return None

    def _inspect_transcript_log(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Safely attempts to read Antigravity transcript.jsonl if accessible.
        Does not crash if missing or permission restricted.
        """
        if not session_id or not self.app_data_dir:
            return None
        transcript_path = os.path.join(
            self.app_data_dir,
            "brain",
            session_id,
            ".system_generated",
            "logs",
            "transcript.jsonl"
        )
        if not os.path.exists(transcript_path):
            return None

        total_tokens = 0
        latest_model = None
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    # Extract token metadata if recorded
                    if "tokens" in entry:
                        t = entry["tokens"]
                        if isinstance(t, dict):
                            total_tokens += t.get("total_tokens", 0)
                        elif isinstance(t, int):
                            total_tokens += t
                    if "model" in entry:
                        latest_model = entry["model"]
            return {
                "tokens_consumed": total_tokens if total_tokens > 0 else None,
                "model_name": latest_model
            }
        except Exception as e:
            logger.debug(f"Could not read Antigravity transcript: {e}")
            return None

    def collect_usage(
        self,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **kwargs
    ) -> AgentUsageMetrics:
        """Collects usage metrics from injected state, transcript logs, or kwargs."""
        key = session_id or task_id or "default"
        if key in self.injected_metrics:
            return self.injected_metrics[key]

        # Check explicit kwargs
        explicit_tokens = kwargs.get("tokens_consumed")
        explicit_capacity = kwargs.get("context_window_capacity")
        explicit_model = kwargs.get("model_name") or self.default_model
        explicit_quota = kwargs.get("account_quota_info")
        explicit_percentage = kwargs.get("usage_percentage")

        if explicit_tokens is not None or explicit_capacity is not None or explicit_percentage is not None:
            capacity = explicit_capacity or self.lookup_model_capacity(explicit_model)
            metrics = AgentUsageMetrics(
                agent_name=self.agent_name,
                session_id=session_id,
                task_id=task_id,
                model_name=explicit_model,
                context_window_capacity=capacity,
                tokens_consumed=explicit_tokens,
                usage_percentage=explicit_percentage,
                account_quota_info=explicit_quota,
                source="app_server"
            )
            return metrics

        # Inspect transcript log if available
        if session_id:
            parsed = self._inspect_transcript_log(session_id)
            if parsed and parsed.get("tokens_consumed") is not None:
                model = parsed.get("model_name") or explicit_model
                capacity = self.lookup_model_capacity(model)
                return AgentUsageMetrics(
                    agent_name=self.agent_name,
                    session_id=session_id,
                    task_id=task_id,
                    model_name=model,
                    context_window_capacity=capacity,
                    tokens_consumed=parsed["tokens_consumed"],
                    source="transcript"
                )

        # Unavailable telemetry -> represent as unknown (None)
        return AgentUsageMetrics(
            agent_name=self.agent_name,
            session_id=session_id,
            task_id=task_id,
            model_name=explicit_model,
            context_window_capacity=self.lookup_model_capacity(explicit_model),
            tokens_consumed=None,
            usage_percentage=None,
            account_quota_info=explicit_quota,
            source="unknown"
        )

    def notify_agent(
        self,
        warning_level: str,
        message: str,
        task_id: Optional[str] = None
    ) -> bool:
        """Records agent notification into buffer."""
        record = {
            "agent": self.agent_name,
            "task_id": task_id,
            "warning_level": warning_level,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.notifications.append(record)
        logger.info(f"[Antigravity Notification] Level: {warning_level} - {message}")
        return True

