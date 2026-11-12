from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class SourceType(str, Enum):
    AGENT = "agent"
    USER = "user"
    DOCUMENT = "document"
    TOOL = "tool"

class SourceMetadata(BaseModel):
    """Provenance metadata tracking who created the information and its initial trust."""
    model_config = ConfigDict(extra="forbid")

    type: SourceType
    actor: str = Field(..., min_length=1, description="Agent identifier, user name, or doc title")
    trust_level: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: Optional[datetime] = None

class MessageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str
    content: str
    message_ref: Optional[str] = None

class DocumentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = None
    content: str
    uri: Optional[str] = None

class ToolOutputPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    output: str
    call_id: Optional[str] = None

class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: SourceMetadata
    messages: Optional[List[MessageItem]] = None
    document: Optional[DocumentPayload] = None
    tool_output: Optional[ToolOutputPayload] = None
    content: Optional[str] = None

class IngestResponse(BaseModel):
    status: str
    source_id: str
    memories: List[Dict[str, Any]]

