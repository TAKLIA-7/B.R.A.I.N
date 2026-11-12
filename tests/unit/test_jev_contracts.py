import pytest
from pydantic import ValidationError
from core.jev.contracts import (
    MemoryDecision,
    RetrievalDecision,
    HandoverDecision,
    ConflictDecision,
    IngestionAnalysisItem
)

def test_valid_memory_decision():
    decision = MemoryDecision(
        memory_type="decision",
        lifetime="persistent",
        importance=0.9,
        confidence=0.95,
        scope="architecture",
        storage_targets=["postgres", "pgvector", "neo4j"],
        requires_semantic_search=True,
        has_meaningful_relationships=True,
        requires_confirmation=False,
        epistemic_assessment="confirmed",
        reasoning="Architectural choice with high confidence and relationships."
    )
    assert decision.memory_type == "decision"
    assert decision.storage_targets == ["postgres", "pgvector", "neo4j"]
    assert decision.importance == 0.9

def test_memory_decision_rejects_extra_fields():
    with pytest.raises(ValidationError):
        MemoryDecision(
            memory_type="decision",
            lifetime="persistent",
            importance=0.8,
            confidence=0.8,
            scope="project",
            storage_targets=["postgres"],
            requires_semantic_search=True,
            has_meaningful_relationships=False,
            requires_confirmation=False,
            epistemic_assessment="asserted",
            reasoning="valid",
            hallucinated_extra_field="rejected"
        )

def test_memory_decision_validates_numerical_bounds():
    with pytest.raises(ValidationError):
        MemoryDecision(
            memory_type="fact",
            lifetime="persistent",
            importance=1.5,  # must be <= 1.0
            confidence=0.8,
            scope="project",
            storage_targets=["postgres"],
            requires_semantic_search=False,
            has_meaningful_relationships=False,
            requires_confirmation=False,
            epistemic_assessment="asserted",
            reasoning="out of bounds"
        )

def test_valid_retrieval_decision():
    decision = RetrievalDecision(
        retrieval_strategy="hybrid",
        include_semantic_search=True,
        include_keyword_search=False,
        include_graph_search=True,
        selected_memory_ids=["mem-001", "mem-002"],
        priority_memory_types=["decision", "fact"],
        token_budget=500,
        abstain=False,
        reasoning="Query benefits from semantic matching and Neo4j graph traversal."
    )
    assert decision.retrieval_strategy == "hybrid"
    assert len(decision.selected_memory_ids) == 2
    assert decision.abstain is False

def test_retrieval_decision_abstention():
    decision = RetrievalDecision(
        retrieval_strategy="keyword",
        include_semantic_search=False,
        include_keyword_search=False,
        include_graph_search=False,
        selected_memory_ids=[],
        priority_memory_types=[],
        token_budget=200,
        abstain=True,
        reasoning="No supporting evidence found in memory store."
    )
    assert decision.abstain is True
    assert len(decision.selected_memory_ids) == 0

def test_valid_handover_decision():
    decision = HandoverDecision(
        task_id="task-42",
        selected_checkpoint_id="cp-v3",
        relevant_memory_ids=["mem-101"],
        relevant_bug_ids=["BUG-01"],
        relevant_fix_ids=["FIX-01"],
        unresolved_questions=["How to handle connection retries?"],
        token_budget=1000,
        reasoning="Resuming task with latest checkpoint and bug fix context."
    )
    assert decision.task_id == "task-42"
    assert decision.selected_checkpoint_id == "cp-v3"
    assert decision.relevant_bug_ids == ["BUG-01"]

def test_valid_conflict_decision():
    decision = ConflictDecision(
        conflict_detected=True,
        conflicting_memory_id="mem-existing-99",
        resolution="supersede",
        assigned_epistemic_state="confirmed",
        reasoning="New evidence with high trust supersedes older claim."
    )
    assert decision.conflict_detected is True
    assert decision.resolution == "supersede"

def test_ingestion_analysis_item():
    item = IngestionAnalysisItem(
        text="PostgreSQL chosen as canonical store",
        subject="PostgreSQL",
        predicate="chosen_as",
        object="canonical_store",
        decision=MemoryDecision(
            memory_type="decision",
            lifetime="persistent",
            importance=0.9,
            confidence=0.95,
            scope="architecture",
            storage_targets=["postgres", "pgvector", "neo4j"],
            requires_semantic_search=True,
            has_meaningful_relationships=True,
            requires_confirmation=False,
            epistemic_assessment="confirmed",
            reasoning="Definitive decision"
        )
    )
    assert item.decision.storage_targets == ["postgres", "pgvector", "neo4j"]

