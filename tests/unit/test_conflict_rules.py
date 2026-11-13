"""
tests/unit/test_conflict_rules.py
Unit tests for deterministic human-in-the-loop conflict approval rules.
Verifies that ambiguous phrasing, insufficient evidence, critical domain impact,
and requirement contradictions trigger mandatory human approval.
"""
import pytest
from core.conflict.rules import (
    MandatoryApprovalEvaluator,
    RULE_AMBIGUOUS_INSTRUCTION,
    RULE_INSUFFICIENT_EVIDENCE,
    RULE_UNSPECIFIED_TIMING,
    RULE_REQUIREMENT_CONTRADICTION,
    RULE_CRITICAL_ARCHITECTURE_IMPACT,
    RULE_UNRELIABLE_JEV_RESOLUTION,
    RULE_MISSING_TARGET_STATE
)
from core.conflict.schemas import (
    ConflictState,
    ConflictResolution,
    ConflictApprovalItem,
    HumanApprovalAction
)


def test_rule_ambiguous_instruction():
    """Verify ambiguous phrasing triggers mandatory approval."""
    claim = "Maybe we should switch our caching layer to Memcached."
    req_approval, rules, reasons = MandatoryApprovalEvaluator.evaluate(
        incoming_claim=claim,
        existing_memories=[{"id": "mem-1", "text": "We use Redis for caching"}],
        conflicting_requirements=[]
    )
    assert req_approval is True
    assert RULE_AMBIGUOUS_INSTRUCTION in rules
    assert "caching" in claim or "Memcached" in claim


def test_rule_unspecified_timing():
    """Verify planned / WIP phrasing triggers mandatory approval."""
    claim = "We are planning to migrate authentication from JWT to session cookies."
    req_approval, rules, reasons = MandatoryApprovalEvaluator.evaluate(
        incoming_claim=claim,
        existing_memories=[{"id": "mem-2", "text": "We use JWT authentication"}],
        conflicting_requirements=[]
    )
    assert req_approval is True
    assert RULE_UNSPECIFIED_TIMING in rules


def test_rule_critical_architecture_impact():
    """Verify database, auth, and security claims trigger critical architecture impact rule."""
    claim = "Switch database engine to MongoDB."
    req_approval, rules, reasons = MandatoryApprovalEvaluator.evaluate(
        incoming_claim=claim,
        existing_memories=[{"id": "mem-3", "text": "Database is PostgreSQL"}],
        conflicting_requirements=[]
    )
    assert req_approval is True
    assert RULE_CRITICAL_ARCHITECTURE_IMPACT in rules


def test_rule_requirement_contradiction():
    """Verify contradiction with an approved project requirement triggers approval."""
    claim = "Disable OAuth2 token expiry validation."
    conflicting_reqs = [{"req_id": "REQ-AUTH-001", "title": "OAuth2 Token Validation"}]
    req_approval, rules, reasons = MandatoryApprovalEvaluator.evaluate(
        incoming_claim=claim,
        existing_memories=[],
        conflicting_requirements=conflicting_reqs
    )
    assert req_approval is True
    assert RULE_REQUIREMENT_CONTRADICTION in rules


def test_rule_insufficient_evidence():
    """Verify contradiction without empirical test proof or trust delta triggers approval."""
    claim = "API port changed to 9090."
    existing = [{"id": "mem-4", "text": "API port is 8000", "trust_level": 0.8}]
    req_approval, rules, reasons = MandatoryApprovalEvaluator.evaluate(
        incoming_claim=claim,
        existing_memories=existing,
        conflicting_requirements=[],
        evidence_and_provenance={},  # No test proof
        new_trust_level=0.85  # delta is only 0.05
    )
    assert req_approval is True
    assert RULE_INSUFFICIENT_EVIDENCE in rules


def test_llm_confidence_cannot_override_rules():
    """Verify that high LLM confidence score cannot override mandatory approval rules."""
    claim = "Probably use SQLite in production."
    req_approval, rules, reasons = MandatoryApprovalEvaluator.evaluate(
        incoming_claim=claim,
        existing_memories=[{"id": "mem-5", "text": "PostgreSQL is our production database"}],
        conflicting_requirements=[],
        jev_proposed_resolution="supersede",
        jev_confidence=0.99  # Very high LLM confidence
    )
    # Must still require approval because claim is ambiguous and critical domain
    assert req_approval is True
    assert RULE_AMBIGUOUS_INSTRUCTION in rules
    assert RULE_CRITICAL_ARCHITECTURE_IMPACT in rules


def test_terse_claim_missing_target_state():
    """Verify overly terse or vague claims trigger missing target state rule."""
    claim = "change db"
    req_approval, rules, reasons = MandatoryApprovalEvaluator.evaluate(
        incoming_claim=claim,
        existing_memories=[{"id": "mem-6", "text": "PostgreSQL is database"}],
        conflicting_requirements=[]
    )
    assert req_approval is True
    assert RULE_MISSING_TARGET_STATE in rules

