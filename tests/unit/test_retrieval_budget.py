import pytest
from core.retrieve.context_budget import ContextBudgetManager, RetrievedItem

def test_token_estimation():
    bm = ContextBudgetManager()
    text = "Knowledge Brain persistent memory layer"
    tokens, is_estimate = bm.estimate_tokens(text)
    assert tokens > 0
    assert is_estimate is True  # Labeled as estimate when exact provider tokenizer is not loaded

def test_token_budget_enforcement():
    bm = ContextBudgetManager()
    
    # Create several retrieved items
    items = [
        RetrievedItem(id="1", text="First item: short text", score=0.9, epistemic_state="confirmed", provenance="alice"),
        RetrievedItem(id="2", text="Second item: longer description with more details about architecture", score=0.8, epistemic_state="asserted", provenance="bob"),
        RetrievedItem(id="3", text="Third item: additional context about storage routing and database", score=0.7, epistemic_state="asserted", provenance="agent-claude"),
        RetrievedItem(id="4", text="Fourth item: this should be truncated if budget is small", score=0.6, epistemic_state="asserted", provenance="doc")
    ]
    
    # Budget of only 25 tokens: should fit first 1-2 items and exclude the rest
    compact_context, total_tokens = bm.build_compact_context(items, token_budget=25)
    assert total_tokens <= 25
    assert len(compact_context) < len(items)
    assert compact_context[0]["id"] == "1"

def test_abstention_on_weak_evidence():
    bm = ContextBudgetManager()
    # No items or items below threshold
    weak_items = [
        RetrievedItem(id="1", text="Unrelated text about weather", score=0.2, epistemic_state="asserted", provenance="untrusted")
    ]
    result = bm.format_search_response(weak_items, token_budget=500, min_score_threshold=0.5)
    assert result["abstain"] is True
    assert result["message"] == "no supporting memory"
    assert len(result["memories"]) == 0

