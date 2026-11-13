from enum import Enum
from typing import List, Optional, Literal, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict

class StepStatus(str, Enum):
    DONE = "done"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"

class CheckpointStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: Union[Literal["done", "in_progress", "pending"], StepStatus]
    state: str
    evidence: List[str] = Field(default_factory=list)

class CheckpointDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    what: str
    why: str
    source: str

class RejectedApproach(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option: str
    reason: str

class CheckpointState(BaseModel):
    """
    Strict cross-agent checkpoint and handover schema.
    Rejects unexpected fields and enforces valid step statuses.
    """
    model_config = ConfigDict(extra="forbid")

    task_id: str
    goal: str
    steps: List[CheckpointStep]
    decisions: List[CheckpointDecision]
    rejected: List[RejectedApproach]
    open_questions: List[str] = Field(default_factory=list)
    written_by: str
    project_files: List[str] = Field(default_factory=list)
    test_results: List[str] = Field(default_factory=list)
    git_commit: Optional[str] = None
    git_branch: Optional[str] = None

class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    requesting_agent: str = "agent"
    token_budget: int = Field(default=4000, ge=50, le=32000)

class ResumeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_id: str
    goal: Optional[str] = None
    checkpoint_version: int
    latest_version: Optional[int] = None
    version: Optional[int] = None
    previous_agent: str
    checkpoint_written_by: Optional[str] = None
    requesting_agent: str
    completed_steps: List[str]
    pending_steps: List[str]
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    decisions: List[Any] = Field(default_factory=list)
    rejected_approaches: List[str] = Field(default_factory=list)
    rejected: List[Dict[str, Any]] = Field(default_factory=list)
    related_bugs: List[Dict[str, Any]] = Field(default_factory=list)
    matching_bugs: List[Dict[str, Any]] = Field(default_factory=list)
    verified_fixes: List[Dict[str, Any]] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    handover_context: str
    token_budget: Optional[int] = None
    is_stale: bool = False
    target_requirement_id: Optional[str] = None
    target_requirement_version: Optional[int] = None
    staleness_warning: Optional[str] = None

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

# Backward compatibility aliases
HandoverState = CheckpointState
StepItem = CheckpointStep
DecisionItem = CheckpointDecision
RejectedOption = RejectedApproach
