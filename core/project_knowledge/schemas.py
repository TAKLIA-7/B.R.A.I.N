from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict

class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, description="Unique project slug, e.g. ecommerce or knowledge-brain")
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    repository_url: Optional[str] = None
    root_path: Optional[str] = None

class ProjectItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: Optional[str] = None
    repository_url: Optional[str] = None
    root_path: Optional[str] = None
    status: str
    created_at: str
    updated_at: str

class ProjectDocumentItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    document_type: str
    relative_path: str
    version: int
    content_hash: str
    status: str
    last_synced_at: str

class DocumentSyncResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str
    synced_count: int
    updated_files: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    status: str = "success"

class ProjectContextResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str
    project_name: str
    task_focus: Optional[str] = None
    project_overview: str
    architecture: str
    tech_stack: str
    active_requirements: List[Dict[str, Any]] = Field(default_factory=list)
    decisions: List[Dict[str, Any]] = Field(default_factory=list)
    related_bugs: List[Dict[str, Any]] = Field(default_factory=list)
    context_markdown: str
    token_budget: int
    estimated_tokens: int

