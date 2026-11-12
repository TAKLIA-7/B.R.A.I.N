import pytest
from pydantic import ValidationError
from core.models.memory import (
    ExtractedMemoryCandidate,
    MemoryType,
    EpistemicState,
    MemoryStatus
)
from core.models.ingest import (
    SourceMetadata,
    SourceType,
    IngestRequest,
    MessageItem
)

def test_valid_memory_candidate():
    candidate = ExtractedMemoryCandidate(
        type=MemoryType.FACT,
        subject="PostgreSQL",
        predicate="uses_port",
        object="5432",
        text="PostgreSQL default port is 5432",
        importance=0.8,
        confidence=0.95
    )
    assert candidate.type == MemoryType.FACT
    assert candidate.subject == "PostgreSQL"
    assert candidate.confidence == 0.95

def test_all_memory_types_supported():
    for mem_type in [
        MemoryType.FACT,
        MemoryType.PREFERENCE,
        MemoryType.DECISION,
        MemoryType.TASK,
        MemoryType.EXPERIENCE,
        MemoryType.PROCEDURE
    ]:
        c = ExtractedMemoryCandidate(
            type=mem_type,
            text=f"Test memory of type {mem_type.value}"
        )
        assert c.type == mem_type

def test_candidate_rejects_extra_fields():
    """Strict validation: LLMs must not invent arbitrary hallucinated fields."""
    with pytest.raises(ValidationError):
        ExtractedMemoryCandidate(
            type=MemoryType.FACT,
            text="Valid text",
            hallucinated_database_choice="arbitrary_db"  # forbidden
        )

def test_candidate_rejects_invalid_type():
    with pytest.raises(ValidationError):
        ExtractedMemoryCandidate(
            type="INVALID_TYPE",
            text="Invalid type test"
        )

def test_ingest_request_validation():
    req = IngestRequest(
        source=SourceMetadata(
            type=SourceType.AGENT,
            actor="agent-claude",
            trust_level=0.7
        ),
        messages=[
            MessageItem(role="assistant", content="I chose FastAPI for the REST backend.")
        ]
    )
    assert req.source.actor == "agent-claude"
    assert req.source.type == SourceType.AGENT
    assert len(req.messages) == 1

def test_source_metadata_trust_bounds():
    with pytest.raises(ValidationError):
        SourceMetadata(
            type=SourceType.USER,
            actor="alice",
            trust_level=1.5  # must be between 0.0 and 1.0
        )

