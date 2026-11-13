"""
core/agent_monitor
Proactive AI agent usage monitoring and automatic checkpointing architecture.
"""
from core.agent_monitor.base_adapter import (
    BaseAgentAdapter,
    AgentUsageMetrics,
    TriggerReason
)
from core.agent_monitor.antigravity_adapter import AntigravityAdapter
from core.agent_monitor.codex_adapter import CodexAdapter
from core.agent_monitor.git_inspector import GitInspector, GitWorkingTreeState
from core.agent_monitor.checkpoint_generator import CheckpointMarkdownGenerator
from core.agent_monitor.usage_monitor import UsageMonitor, CheckpointPolicy
from core.agent_monitor.checkpoint_scheduler import CheckpointScheduler

__all__ = [
    "BaseAgentAdapter",
    "AgentUsageMetrics",
    "TriggerReason",
    "AntigravityAdapter",
    "CodexAdapter",
    "GitInspector",
    "GitWorkingTreeState",
    "CheckpointMarkdownGenerator",
    "UsageMonitor",
    "CheckpointPolicy",
    "CheckpointScheduler"
]

