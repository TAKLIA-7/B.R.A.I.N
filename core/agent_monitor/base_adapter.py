"""
core/agent_monitor/base_adapter.py
Defines the base interface for agent monitoring adapters and standardized usage telemetry models.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class TriggerReason(str, Enum):
    THRESHOLD_70_PREPARE = "threshold_70_prepare"
    THRESHOLD_80_AUTO = "threshold_80_auto"
    THRESHOLD_90_URGENT = "threshold_90_urgent"
    THRESHOLD_95_CRITICAL = "threshold_95_critical"
    EVENT_COMPACTION_IMMINENT = "event_compaction_imminent"
    EVENT_SESSION_END = "event_session_end"
    FALLBACK_PERIODIC = "fallback_periodic"
    FALLBACK_TASK_BOUNDARY = "fallback_task_boundary"
    MANUAL_ASSISTED = "manual_assisted"


class AgentUsageMetrics(BaseModel):
    """
    Standardized usage telemetry across AI coding agents.
    Unavailable metrics must remain None (unknown). Never invent token counts.
    """
    model_config = ConfigDict(extra="ignore")

    agent_name: str
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    model_name: Optional[str] = None
    context_window_capacity: Optional[int] = Field(default=None, ge=1)
    tokens_consumed: Optional[int] = Field(default=None, ge=0)
    remaining_context_capacity: Optional[int] = Field(default=None, ge=0)
    usage_percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    account_quota_info: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "unknown"  # "sdk", "lifecycle_event", "app_server", "simulated", "transcript", "unknown"

    def is_context_percentage_known(self) -> bool:
        """Returns True if context usage percentage is known or can be calculated."""
        if self.usage_percentage is not None:
            return True
        return (
            self.tokens_consumed is not None
            and self.context_window_capacity is not None
            and self.context_window_capacity > 0
        )

    def get_effective_usage_percentage(self) -> Optional[float]:
        """Calculates or returns the usage percentage, rounded to 2 decimal places."""
        if self.usage_percentage is not None:
            return round(self.usage_percentage, 2)
        if (
            self.tokens_consumed is not None
            and self.context_window_capacity is not None
            and self.context_window_capacity > 0
        ):
            calc = (self.tokens_consumed / self.context_window_capacity) * 100.0
            return round(min(100.0, max(0.0, calc)), 2)
        return None

    def get_remaining_capacity(self) -> Optional[int]:
        """Returns remaining context capacity."""
        if self.remaining_context_capacity is not None:
            return self.remaining_context_capacity
        if (
            self.context_window_capacity is not None
            and self.tokens_consumed is not None
        ):
            return max(0, self.context_window_capacity - self.tokens_consumed)
        return None


class BaseAgentAdapter(ABC):
    """Abstract adapter interface for AI coding agent usage monitoring."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name

    def get_agent_name(self) -> str:
        return self.agent_name

    @abstractmethod
    def collect_usage(
        self,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **kwargs
    ) -> AgentUsageMetrics:
        """
        Collect current context window and token usage from the agent.
        Unavailable metrics must be returned as None.
        """
        pass

    def supports_token_counting(self) -> bool:
        """Whether this adapter has access to real-time token counts."""
        return True

    def supports_lifecycle_events(self) -> bool:
        """Whether this adapter supports lifecycle/compaction events."""
        return True

    def notify_agent(
        self,
        warning_level: str,
        message: str,
        task_id: Optional[str] = None
    ) -> bool:
        """
        Sends an in-band or out-of-band notification or warning to the agent.
        Returns True if delivered, False if unhandled.
        """
        return False

