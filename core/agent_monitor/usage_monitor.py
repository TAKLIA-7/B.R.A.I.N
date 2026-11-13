"""
core/agent_monitor/usage_monitor.py
Monitors AI agent usage telemetry, enforces configurable thresholds, and manages cooldowns and event triggers.
"""
import time
import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from core.agent_monitor.base_adapter import (
    BaseAgentAdapter,
    AgentUsageMetrics,
    TriggerReason
)
from core.agent_monitor.antigravity_adapter import AntigravityAdapter
from core.agent_monitor.codex_adapter import CodexAdapter

logger = logging.getLogger(__name__)


class CheckpointPolicy(BaseModel):
    """Configurable checkpoint trigger thresholds and cooldown settings."""
    prepare_threshold: float = Field(default=70.0, ge=1.0, le=100.0)
    auto_checkpoint_threshold: float = Field(default=80.0, ge=1.0, le=100.0)
    urgent_threshold: float = Field(default=90.0, ge=1.0, le=100.0)
    critical_threshold: float = Field(default=95.0, ge=1.0, le=100.0)
    cooldown_seconds: int = Field(default=60, ge=0)
    enable_event_triggers: bool = True
    fallback_to_periodic: bool = True
    periodic_interval_seconds: int = Field(default=300, ge=10)


class UsageMonitor:
    """
    Central monitor that evaluates agent context window metrics against policy thresholds.
    Applies cooldowns, deduplication, and lifecycle fallback logic.
    """

    def __init__(self, policy: Optional[CheckpointPolicy] = None):
        self.policy = policy or CheckpointPolicy()
        self.adapters: Dict[str, BaseAgentAdapter] = {}
        # task_id -> { "last_trigger_time": float, "last_reason": TriggerReason, "highest_level": float }
        self._task_history: Dict[str, Dict[str, Any]] = {}

        # Register default native adapters
        self.register_adapter(AntigravityAdapter())
        self.register_adapter(CodexAdapter())

    def register_adapter(self, adapter: BaseAgentAdapter) -> None:
        """Registers or replaces an agent adapter."""
        self.adapters[adapter.get_agent_name().lower()] = adapter
        logger.info(f"Registered agent monitor adapter: {adapter.get_agent_name()}")

    def get_adapter(self, agent_name: str) -> Optional[BaseAgentAdapter]:
        return self.adapters.get(agent_name.lower())

    def update_policy(self, **kwargs) -> None:
        """Allows dynamic policy threshold reconfiguration."""
        current = self.policy.model_dump()
        current.update(kwargs)
        self.policy = CheckpointPolicy.model_validate(current)

    def evaluate_metrics(
        self,
        metrics: AgentUsageMetrics,
        force: bool = False
    ) -> Optional[TriggerReason]:
        """
        Evaluates metrics against threshold policies.
        Returns TriggerReason if a checkpoint must occur, or None if skipped/cooldown active.
        """
        task_id = metrics.task_id or metrics.session_id or "default"
        now = time.time()
        history = self._task_history.get(task_id, {
            "last_trigger_time": 0.0,
            "last_reason": None,
            "last_percentage": 0.0
        })

        # 1. Check if percentage is known
        pct = metrics.get_effective_usage_percentage()
        if pct is None:
            # Telemetry is unknown. Check fallback policy if enabled
            if self.policy.fallback_to_periodic:
                elapsed = now - history["last_trigger_time"]
                if elapsed >= self.policy.periodic_interval_seconds or force:
                    self._record_trigger(task_id, TriggerReason.FALLBACK_PERIODIC, 0.0, now)
                    return TriggerReason.FALLBACK_PERIODIC
            return None

        # 2. Determine target trigger reason based on thresholds
        reason: Optional[TriggerReason] = None
        if pct >= self.policy.critical_threshold:
            reason = TriggerReason.THRESHOLD_95_CRITICAL
        elif pct >= self.policy.urgent_threshold:
            reason = TriggerReason.THRESHOLD_90_URGENT
        elif pct >= self.policy.auto_checkpoint_threshold:
            reason = TriggerReason.THRESHOLD_80_AUTO
        elif pct >= self.policy.prepare_threshold:
            reason = TriggerReason.THRESHOLD_70_PREPARE

        if not reason:
            return None

        if force:
            self._record_trigger(task_id, reason, pct, now)
            return reason

        # 3. Deduplication & Cooldown logic:
        # Avoid repeated triggers at the same level within cooldown period
        elapsed = now - history["last_trigger_time"]
        last_reason = history["last_reason"]
        last_pct = history["last_percentage"]

        # Escalate immediately if moving to a higher severity threshold even within cooldown
        is_escalation = (
            reason == TriggerReason.THRESHOLD_95_CRITICAL and last_reason != TriggerReason.THRESHOLD_95_CRITICAL
        ) or (
            reason == TriggerReason.THRESHOLD_90_URGENT and last_reason in [TriggerReason.THRESHOLD_70_PREPARE, TriggerReason.THRESHOLD_80_AUTO]
        ) or (
            reason == TriggerReason.THRESHOLD_80_AUTO and last_reason == TriggerReason.THRESHOLD_70_PREPARE
        )

        if not is_escalation:
            # Check cooldown
            if elapsed < self.policy.cooldown_seconds:
                logger.debug(f"Checkpoint for {task_id} suppressed by cooldown ({elapsed:.1f}s < {self.policy.cooldown_seconds}s)")
                return None
            # If percentage has not grown meaningfully since last checkpoint, suppress duplicate
            if abs(pct - last_pct) < 1.0 and last_reason == reason:
                logger.debug(f"Checkpoint for {task_id} suppressed by deduplication (pct {pct}% == {last_pct}%)")
                return None

        self._record_trigger(task_id, reason, pct, now)
        return reason

    def evaluate_lifecycle_event(
        self,
        event_name: str,
        task_id: str,
        agent_name: str = "agent"
    ) -> Optional[TriggerReason]:
        """Handles explicit agent lifecycle events (e.g. context compaction, session end)."""
        if not self.policy.enable_event_triggers:
            return None

        now = time.time()
        event_lower = event_name.lower()
        reason: Optional[TriggerReason] = None

        if "compact" in event_lower or "prune" in event_lower:
            reason = TriggerReason.EVENT_COMPACTION_IMMINENT
        elif "end" in event_lower or "close" in event_lower or "terminate" in event_lower:
            reason = TriggerReason.EVENT_SESSION_END
        elif "boundary" in event_lower or "milestone" in event_lower:
            reason = TriggerReason.FALLBACK_TASK_BOUNDARY

        if reason:
            self._record_trigger(task_id, reason, 0.0, now)
            return reason
        return None

    def _record_trigger(
        self,
        task_id: str,
        reason: TriggerReason,
        percentage: float,
        timestamp: float
    ) -> None:
        self._task_history[task_id] = {
            "last_trigger_time": timestamp,
            "last_reason": reason,
            "last_percentage": percentage
        }

