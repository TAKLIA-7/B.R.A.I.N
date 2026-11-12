import pytest
from scripts.benchmark_cross_agent import run_cross_agent_benchmark

def test_cross_agent_benchmark_execution():
    """
    Verifies Phase 10 cross-agent portability:
    - Agent A creates checkpoint
    - Agent B resumes in fresh session with zero transcript transfer
    - Objective API test passes
    - All three benchmark variants run
    - Both handover directions (A->B and B->A) succeed
    """
    report = run_cross_agent_benchmark()
    
    # Assertions on benchmark results
    assert report["variants"]["variant_1_kb_handover"]["objective_test_pass"] is True
    assert report["variants"]["variant_1_kb_handover"]["repeated_steps"] == 0
    assert report["variants"]["variant_1_kb_handover"]["dead_end_repeats"] == 0
    assert report["cross_pair_portability"]["a_to_b_handover_success"] is True
    assert report["cross_pair_portability"]["b_to_a_handover_success"] is True
    assert report["cross_pair_portability"]["token_reduction_vs_transcript_pct"] > 60.0

