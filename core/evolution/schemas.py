from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class RequirementCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    req_id: str = Field(..., description="Stable requirement identifier, e.g. REQ-AUTH-001")
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    project_id: Optional[str] = None
    module: str = Field(default="general")
    category: Literal["functional", "non_functional", "security", "api", "architecture", "database"] = "functional"
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    acceptance_criteria: List[str] = Field(default_factory=list)
    created_by: str = "user"
    initial_status: Literal["draft", "proposed", "approved"] = "approved"

class RequirementProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    req_id: str
    proposed_description: str = Field(..., min_length=1)
    acceptance_criteria: List[str] = Field(default_factory=list)
    reason: str = Field(..., min_length=1)
    proposed_by: str = "agent"
    source: Optional[str] = None

class RequirementApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    req_id: str
    target_version: int
    decision: Literal["approved", "rejected"]
    approver: str = "lead_architect"
    rationale: Optional[str] = None

class RequirementVersionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    requirement_id: str
    version: int
    description: str
    acceptance_criteria: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    created_by: str
    created_at: str
    approval_status: str
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    supersedes_version: Optional[int] = None

class RequirementItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    req_id: str
    project_id: Optional[str] = None
    module: str
    title: str
    category: str
    priority: str
    current_version: int
    status: str
    created_at: str
    updated_at: str
    current_description: Optional[str] = None
    acceptance_criteria: List[str] = Field(default_factory=list)
    versions: List[RequirementVersionItem] = Field(default_factory=list)

class RequirementImpact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    req_id: str
    version: int
    affected_modules: List[str] = Field(default_factory=list)
    affected_files: List[str] = Field(default_factory=list)
    affected_endpoints: List[str] = Field(default_factory=list)
    affected_entities: List[str] = Field(default_factory=list)
    affected_tasks: List[str] = Field(default_factory=list)
    affected_tests: List[str] = Field(default_factory=list)

class ChangeRequestItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    change_id: str
    req_id: str
    target_version: int
    original_value: Optional[str] = None
    proposed_value: str
    reason: str
    source: Optional[str] = None
    proposed_by: str
    status: str
    created_at: str

class TaskStalenessReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_id: str
    is_stale: bool
    target_requirement_id: Optional[str] = None
    target_requirement_version: Optional[int] = None
    latest_requirement_version: Optional[int] = None
    reason: Optional[str] = None

