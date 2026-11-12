from enum import Enum
from typing import List, Any
from pydantic import BaseModel, Field, ConfigDict

class StepStatus(str, Enum):
    DONE = "done"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"

class StepItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    status: StepStatus
    state: str
    evidence: List[Any] = Field(default_factory=list)

class DecisionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    what: str
    why: str
    source: str

class RejectedOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option: str
    reason: str

class HandoverState(BaseModel):
    """
    Strict cross-agent handover schema according to Section F.
    Rejects invalid step status values and arbitrary hallucinated fields.
    """
    model_config = ConfigDict(extra="forbid")

    task_id: str
    goal: str
    steps: List[StepItem]
    decisions: List[DecisionItem]
    rejected: List[RejectedOption]
    open_questions: List[str]
    written_by: str

