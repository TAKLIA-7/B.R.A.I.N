from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    DECISION = "decision"
    TASK = "task"
    EXPERIENCE = "experience"
    PROCEDURE = "procedure"

class EpistemicState(str, Enum):
    ASSERTED = "asserted"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"

class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DELETED = "deleted"

class ExtractedMemoryCandidate(BaseModel):
    """Memory candidate extracted from content by LLM, strictly validated."""
    model_config = ConfigDict(extra="forbid")

    type: MemoryType
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    text: str = Field(..., min_length=1, description="Normalized memory statement or claim")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    message_ref: Optional[str] = None
    requires_semantic_search: bool = True
    has_meaningful_relationships: bool = False
    resumable: bool = False

class StoredMemory(BaseModel):
    """Canonical persistent memory record stored in PostgreSQL."""
    id: str
    type: MemoryType
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    text: str
    status: MemoryStatus = MemoryStatus.ACTIVE
    epistemic_state: EpistemicState = EpistemicState.ASSERTED
    source_id: Optional[str] = None
    message_ref: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    supersedes_id: Optional[str] = None
    created_at: Optional[datetime] = None

