"""
core/conflict
Human-in-the-Loop Conflict Resolution System for Knowledge Brain.
"""
from core.conflict.schemas import (
    ConflictState,
    ConflictResolution,
    ConflictApprovalItem,
    HumanApprovalAction,
    ClarificationRequest
)
from core.conflict.rules import (
    MandatoryApprovalEvaluator,
    RULE_AMBIGUOUS_INSTRUCTION,
    RULE_INSUFFICIENT_EVIDENCE,
    RULE_UNSPECIFIED_TIMING,
    RULE_REQUIREMENT_CONTRADICTION,
    RULE_CRITICAL_ARCHITECTURE_IMPACT,
    RULE_UNRELIABLE_JEV_RESOLUTION,
    RULE_MISSING_TARGET_STATE
)
from core.conflict.detector import ConflictDetector
from core.conflict.manager import ConflictManager

__all__ = [
    "ConflictState",
    "ConflictResolution",
    "ConflictApprovalItem",
    "HumanApprovalAction",
    "ClarificationRequest",
    "MandatoryApprovalEvaluator",
    "ConflictDetector",
    "ConflictManager",
    "RULE_AMBIGUOUS_INSTRUCTION",
    "RULE_INSUFFICIENT_EVIDENCE",
    "RULE_UNSPECIFIED_TIMING",
    "RULE_REQUIREMENT_CONTRADICTION",
    "RULE_CRITICAL_ARCHITECTURE_IMPACT",
    "RULE_UNRELIABLE_JEV_RESOLUTION",
    "RULE_MISSING_TARGET_STATE"
]

