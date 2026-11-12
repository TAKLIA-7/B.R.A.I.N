import pytest
from core.models.memory import EpistemicState, ExtractedMemoryCandidate, MemoryType
from core.models.ingest import SourceMetadata, SourceType
from core.store.provenance import ProvenanceManager

def test_agent_claims_default_to_asserted():
    source = SourceMetadata(type=SourceType.AGENT, actor="agent-claude", trust_level=0.8)
    candidate = ExtractedMemoryCandidate(
        type=MemoryType.DECISION,
        text="Decided to use PostgreSQL for persistent memory"
    )
    pm = ProvenanceManager()
    state = pm.determine_initial_epistemic_state(candidate, source)
    assert state == EpistemicState.ASSERTED

def test_untrusted_document_claims_default_to_asserted():
    source = SourceMetadata(type=SourceType.DOCUMENT, actor="external_doc.pdf", trust_level=0.4)
    candidate = ExtractedMemoryCandidate(
        type=MemoryType.FACT,
        text="The database port is 9999"
    )
    pm = ProvenanceManager()
    state = pm.determine_initial_epistemic_state(candidate, source)
    assert state == EpistemicState.ASSERTED

def test_planted_false_claim_remains_asserted():
    """A planted false claim must retain source attribution and never silently become confirmed."""
    source = SourceMetadata(type=SourceType.DOCUMENT, actor="adversarial_note.txt", trust_level=0.2)
    candidate = ExtractedMemoryCandidate(
        type=MemoryType.FACT,
        text="Planted claim: Neo4j is replaced by MongoDB",
        confidence=0.99  # even if LLM reports high confidence
    )
    pm = ProvenanceManager()
    state = pm.determine_initial_epistemic_state(candidate, source)
    assert state == EpistemicState.ASSERTED
    assert state != EpistemicState.CONFIRMED

def test_verification_evidence_can_confirm():
    source = SourceMetadata(type=SourceType.AGENT, actor="tester", trust_level=0.9)
    candidate = ExtractedMemoryCandidate(
        type=MemoryType.FACT,
        text="Test suite passes with 100% coverage"
    )
    pm = ProvenanceManager()
    # Without verification:
    assert pm.determine_initial_epistemic_state(candidate, source) == EpistemicState.ASSERTED
    # With explicit verification evidence:
    state = pm.evaluate_state_with_evidence(candidate, source, verification_evidence={"test_exit_code": 0})
    assert state == EpistemicState.CONFIRMED

