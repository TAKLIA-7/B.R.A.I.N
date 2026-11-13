"""
core/conflict/schemas.py
Pydantic contracts and data models for Human-in-the-Loop Conflict Resolution in Knowledge Brain.
"""
from enum import Enum
from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import BaseModel, Field, ConfigDict


class ConflictState(str, Enum):
    DETECTED = "detected"
    EVALUATING = "evaluating"
    PENDING_HUMAN_APPROVAL = "pending_human_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLARIFICATION_REQUIRED = "clarification_required"
    RESOLVED = "resolved"


class ConflictResolution(str, Enum):
    SUPERSEDE = "supersede"
    DISPUTE = "dispute"
    COEXIST = "coexist"
    REJECT = "reject"


class ConflictApprovalItem(BaseModel):
    """
    Structured model for conflict approval requests awaiting human arbitration.
    """
    model_config = ConfigDict(extra="ignore")

    conflict_id: str
    project_id: Optional[str] = None
    existing_memory_ids: List[str] = Field(default_factory=list)
    incoming_claim: str
    source_agent: str
    source_session: Optional[str] = None
    evidence_and_provenance: Dict[str, Any] = Field(default_factory=dict)
    proposed_resolution: str = ConflictResolution.DISPUTE.value
    reason_approval_required: str
    applicable_rule_ids: List[str] = Field(default_factory=list)
    potentially_affected_documents: List[str] = Field(default_factory=list)
    potentially_affected_requirements: List[str] = Field(default_factory=list)
    potentially_affected_tasks: List[str] = Field(default_factory=list)
    status: Union[str, ConflictState] = ConflictState.PENDING_HUMAN_APPROVAL
    human_approver: Optional[str] = None
    approval_rationale: Optional[str] = None
    clarification_request: Optional[str] = None
    clarification_response: Optional[str] = None
    execution_status: str = "pending"  # "pending", "executed", "rejected", "skipped"
    synchronization_status: str = "pending"
    existing_state_snapshot: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class HumanApprovalAction(BaseModel):
    """Payload for human decision on a pending conflict."""
    approver: str
    is_human: bool = True
    decision: Literal["approved", "rejected", "clarify"]
    selected_resolution: Optional[str] = None  # supersede, dispute, coexist, reject
    rationale: Optional[str] = None
    clarification_notes: Optional[str] = None


class ClarificationRequest(BaseModel):
    """Payload when submitting additional evidence or clarification for a conflict."""
    author: str
    clarification_notes: str
    updated_claim: Optional[str] = None
    additional_evidence: Optional[Dict[str, Any]] = None

