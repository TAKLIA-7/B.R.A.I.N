from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict

class MemoryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_type: Literal["fact", "preference", "decision", "task", "experience", "procedure"]
    lifetime: Literal["temporary", "persistent"]
    importance: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    scope: str
    storage_targets: List[Literal["postgres", "redis", "pgvector", "neo4j", "obsidian"]]
    requires_semantic_search: bool = True
    has_meaningful_relationships: bool = False
    requires_confirmation: bool = False
    epistemic_assessment: Literal["asserted", "confirmed", "disputed"] = "asserted"
    reasoning: str

class IngestionAnalysisItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    decision: MemoryDecision

class RetrievalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieval_strategy: Literal["semantic", "graph", "hybrid", "keyword"]
    include_semantic_search: bool
    include_keyword_search: bool
    include_graph_search: bool
    selected_memory_ids: List[str] = Field(default_factory=list)
    priority_memory_types: List[str] = Field(default_factory=list)
    token_budget: int = Field(ge=10, le=32000)
    abstain: bool = False
    reasoning: str

class HandoverDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    selected_checkpoint_id: str
    relevant_memory_ids: List[str] = Field(default_factory=list)
    relevant_bug_ids: List[str] = Field(default_factory=list)
    relevant_fix_ids: List[str] = Field(default_factory=list)
    unresolved_questions: List[str] = Field(default_factory=list)
    token_budget: int = Field(ge=50, le=32000)
    reasoning: str

class ConflictDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_detected: bool
    conflicting_memory_id: Optional[str] = None
    resolution: Literal["supersede", "dispute", "coexist", "reject"]
    assigned_epistemic_state: Literal["asserted", "confirmed", "disputed"]
    reasoning: str

