"""
core/agent_monitor/codex_adapter.py
Adapter for OpenAI Codex, OpenAI CLI, and compatible OpenAI API agents.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from core.agent_monitor.base_adapter import BaseAgentAdapter, AgentUsageMetrics

logger = logging.getLogger(__name__)

CODEX_MODEL_CAPACITIES: Dict[str, int] = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "o1": 200000,
    "o1-preview": 128000,
    "o1-mini": 128000,
    "o3-mini": 200000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16384,
}


class CodexAdapter(BaseAgentAdapter):
    """
    Adapter for OpenAI Codex and ChatGPT developer platforms.
    Monitors OpenAI API usage envelopes, headers, and developer sessions.
    """

    def __init__(self, default_model: str = "gpt-4o"):
        super().__init__(agent_name="codex")
        self.default_model = default_model
        self.injected_metrics: Dict[str, AgentUsageMetrics] = {}
        self.notifications: List[Dict[str, Any]] = []

    def set_injected_metrics(self, session_or_task_id: str, metrics: AgentUsageMetrics) -> None:
        """Allow host or API middleware to directly register observed usage."""
        self.injected_metrics[session_or_task_id] = metrics

    def lookup_model_capacity(self, model_name: Optional[str]) -> Optional[int]:
        if not model_name:
            return None
        norm = model_name.lower().replace(" ", "-").replace("_", "-")
        for key, cap in CODEX_MODEL_CAPACITIES.items():
            if key in norm or norm in key:
                return cap
        return None

    def collect_usage(
        self,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **kwargs
    ) -> AgentUsageMetrics:
        """
        Collects usage metrics from injected state, OpenAI API usage response, or headers.
        """
        key = session_id or task_id or "default"
        if key in self.injected_metrics:
            return self.injected_metrics[key]

        # Handle explicit API usage payload from kwargs
        api_usage = kwargs.get("api_usage") or kwargs.get("usage")
        model = kwargs.get("model_name") or self.default_model
        capacity = kwargs.get("context_window_capacity") or self.lookup_model_capacity(model)
        explicit_quota = kwargs.get("account_quota_info")
        explicit_percentage = kwargs.get("usage_percentage")

        if isinstance(api_usage, dict):
            tokens = api_usage.get("total_tokens") or api_usage.get("prompt_tokens")
            return AgentUsageMetrics(
                agent_name=self.agent_name,
                session_id=session_id,
                task_id=task_id,
                model_name=model,
                context_window_capacity=capacity,
                tokens_consumed=tokens,
                usage_percentage=explicit_percentage,
                account_quota_info=explicit_quota,
                source="sdk"
            )

        # Handle direct token arguments
        tokens = kwargs.get("tokens_consumed")
        if tokens is not None or explicit_percentage is not None:
            return AgentUsageMetrics(
                agent_name=self.agent_name,
                session_id=session_id,
                task_id=task_id,
                model_name=model,
                context_window_capacity=capacity,
                tokens_consumed=tokens,
                usage_percentage=explicit_percentage,
                account_quota_info=explicit_quota,
                source="app_server"
            )

        # Telemetry is unavailable -> represent as unknown (None)
        return AgentUsageMetrics(
            agent_name=self.agent_name,
            session_id=session_id,
            task_id=task_id,
            model_name=model,
            context_window_capacity=capacity,
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
        """Records notification into buffer for Codex."""
        record = {
            "agent": self.agent_name,
            "task_id": task_id,
            "warning_level": warning_level,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.notifications.append(record)
        logger.info(f"[Codex Notification] Level: {warning_level} - {message}")
        return True

