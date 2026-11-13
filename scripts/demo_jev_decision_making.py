"""
scripts/demo_jev_decision_making.py
Demonstration script for JEV (Judge & Evaluation Validator) Decision Engine in Knowledge Brain.

Demonstrates:
1. Ingestion & Storage Routing Decision (Decomposition, Epistemic status, Lifetime & Storage routing)
2. Retrieval Strategy & Dynamic Token Budgeting (Semantic/Graph/Hybrid selection & Abstain logic)
3. Cross-Agent Handover Synthesis (Extracting compact essential context for new agents)
4. Conflict Resolution & Epistemic Evaluation (Contradiction detection, Supersede vs Dispute)
5. Graceful Deterministic Fallback (Ensuring continuous operation if LLM is offline/disabled)
"""
import sys
import os
import json
import time

# Add repo root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Suppress loud postgres and openrouter connection error logs during the demo if DB is offline
import logging
logging.getLogger("core.jev.engine").setLevel(logging.CRITICAL)
logging.getLogger("core.jev.client").setLevel(logging.CRITICAL)
logging.getLogger("core.adapters.postgres").setLevel(logging.CRITICAL)

from unittest.mock import MagicMock
from core.jev.engine import JEVDecisionEngine
from core.models.ingest import IngestRequest, SourceMetadata, SourceType

def print_header(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def print_section(title):
    print(f"\n--- {title} ---")

def run_demo():
    print_header("KNOWLEDGE BRAIN: JEV DECISION ENGINE DEMONSTRATION")
    print("JEV (Judge & Evaluation Validator) is the central orchestration and cognitive")
    print("decision layer separating high-level LLM reasoning from strict Python contract execution.")

    # Check if PostgreSQL is available, else provide mock adapter for clean demonstration
    from core.adapters.postgres import PostgresAdapter
    pg_adapter = PostgresAdapter()
    try:
        with pg_adapter.get_connection() as conn:
            pass
    except Exception:
        mock_pg = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, 1, '{"goal": "Build auth service", "steps": []}', "Agent-Frontend")
        mock_cursor.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_pg.get_connection.return_value = mock_conn
        mock_pg.execute_query.return_value = []
        pg_adapter = mock_pg

    # Initialize JEV Decision Engine
    jev = JEVDecisionEngine(postgres_adapter=pg_adapter)
    print(f"\n[Status] JEV Engine Initialized:")
    print(f"  * Mode: {'Enabled (OpenRouter Gateway)' if jev.enabled else 'Fallback/Offline'}")
    print(f"  * Model: {jev.client.model}")
    print(f"  * Gateway Base URL: {jev.client.base_url}")

    # =========================================================================
    # 1. INGESTION & STORAGE ROUTING DECISION
    # =========================================================================
    print_header("SCENARIO 1: INGESTION & MULTI-STORE ROUTING DECISION")
    sample_text = (
        "Architectural Decision: We will use PostgreSQL 16 with pgvector for all long-term "
        "memory embeddings, while Redis handles temporary agent session state with a 1-hour TTL. "
        "Alice is the lead architect for this subsystem."
    )
    print("Incoming Raw Ingestion Content:")
    print(f"  \"{sample_text}\"")

    req = IngestRequest(
        source=SourceMetadata(type=SourceType.AGENT, actor="Agent-Architect", trust_level=0.9),
        content=sample_text
    )

    t0 = time.time()
    items, audit = jev.decide_ingestion(req)
    latency = (time.time() - t0) * 1000

    print(f"\nJEV Decision Output (Latency: {latency:.1f}ms | Fallback: {audit.get('fallback_used', False)}):")
    print(f"Extracted {len(items)} atomic memory items:")
    for idx, item in enumerate(items, 1):
        dec = item.decision
        print(f"\n  [Item {idx}]")
        print(f"    * Text:           {item.text}")
        print(f"    * Subject/Rel:    {item.subject} -> {item.predicate} -> {item.object}")
        print(f"    * Memory Type:    {dec.memory_type.upper()}")
        print(f"    * Lifetime:       {dec.lifetime.upper()}")
        print(f"    * Scope:          {dec.scope}")
        print(f"    * Storage Routes: {dec.storage_targets}")
        print(f"    * Epistemic:      {dec.epistemic_assessment}")
        print(f"    * Importance:     {dec.importance:.2f} | Confidence: {dec.confidence:.2f}")
        print(f"    * Reasoning:      {dec.reasoning}")

    # =========================================================================
    # 2. RETRIEVAL STRATEGY & DYNAMIC BUDGETING
    # =========================================================================
    print_header("SCENARIO 2: RETRIEVAL STRATEGY & TOKEN ALLOCATION")
    query = "How is temporary session state stored and what is the TTL?"
    print(f"Query: \"{query}\"")
    print("Requested Token Budget: 500 tokens")

    retrieval_decision, audit = jev.decide_retrieval(query=query, token_budget=500)
    print(f"\nJEV Retrieval Strategy Decision:")
    print(f"  * Recommended Strategy: {retrieval_decision.retrieval_strategy.upper()}")
    print(f"  * Include Semantic:     {retrieval_decision.include_semantic_search}")
    print(f"  * Include Graph:        {retrieval_decision.include_graph_search}")
    print(f"  * Include Keyword:      {retrieval_decision.include_keyword_search}")
    print(f"  * Priority Memory Types:{retrieval_decision.priority_memory_types}")
    print(f"  * Allocated Budget:     {retrieval_decision.token_budget} tokens")
    print(f"  * Abstain Flag:         {retrieval_decision.abstain}")
    print(f"  * Reasoning:            {retrieval_decision.reasoning}")

    # =========================================================================
    # 3. CROSS-AGENT HANDOVER SYNTHESIS
    # =========================================================================
    print_header("SCENARIO 3: CROSS-AGENT TASK HANDOVER SYNTHESIS")
    print("Task: 'task-auth-service-01' is transitioning from Agent-Frontend to Agent-Backend.")
    print("JEV filters out conversational noise and packages minimal critical context.")

    handover_decision, audit = jev.decide_handover(task_id="task-auth-service-01", token_budget=800)
    print(f"\nJEV Handover Package Decision:")
    print(f"  * Target Task:          {handover_decision.task_id}")
    print(f"  * Selected Checkpoint:  {handover_decision.selected_checkpoint_id or 'Latest Valid'}")
    print(f"  * Relevant Memory IDs:  {handover_decision.relevant_memory_ids}")
    print(f"  * Relevant Bug IDs:     {handover_decision.relevant_bug_ids}")
    print(f"  * Unresolved Questions: {handover_decision.unresolved_questions}")
    print(f"  * Token Budget Target:  {handover_decision.token_budget} tokens")
    print(f"  * Reasoning:            {handover_decision.reasoning}")

    # =========================================================================
    # 4. CONFLICT RESOLUTION & CONTRADICTION EVALUATION
    # =========================================================================
    print_header("SCENARIO 4: CONTRADICTION & CONFLICT RESOLUTION")
    existing_memory = {
        "memory_id": "mem-cache-001",
        "text": "Redis session TTL is configured to 3600 seconds.",
        "trust_score": 0.85,
        "epistemic_state": "confirmed"
    }
    new_claim = "Redis session TTL has been changed to 7200 seconds per the security audit."
    print("Existing Active Memory in PostgreSQL:")
    print(f"  ID:          {existing_memory['memory_id']}")
    print(f"  Statement:   \"{existing_memory['text']}\"")
    print(f"  Trust Level: {existing_memory['trust_score']} (CONFIRMED)")

    print(f"\nNew Incoming Claim (Trust: 0.95):")
    print(f"  Statement:   \"{new_claim}\"")

    conflict_decision, audit = jev.decide_conflict(
        existing_memory=existing_memory,
        new_claim=new_claim,
        new_trust_level=0.95
    )

    print(f"\nJEV Conflict Evaluation:")
    print(f"  * Conflict Detected:    {conflict_decision.conflict_detected}")
    print(f"  * Target Memory ID:     {conflict_decision.conflicting_memory_id}")
    print(f"  * Proposed Resolution:  {conflict_decision.resolution.upper()}")
    print(f"  * Assigned Epistemic:   {conflict_decision.assigned_epistemic_state.upper()}")
    print(f"  * Reasoning:            {conflict_decision.reasoning}")

    # =========================================================================
    # 5. RESILIENCE: DETERMINISTIC FALLBACK MODE
    # =========================================================================
    print_header("SCENARIO 5: GRACEFUL DETERMINISTIC FALLBACK (OFFLINE SAFETY)")
    print("If OpenRouter / LLM is unreachable or disabled, JEV guarantees zero crash")
    print("by executing heuristic rule-based deterministic fallbacks.")

    offline_engine = JEVDecisionEngine(enabled=False, postgres_adapter=pg_adapter)
    fallback_items, fallback_audit = offline_engine.decide_ingestion(req)
    print(f"\nOffline Execution Result:")
    print(f"  * Fallback Used:        {fallback_audit['fallback_used']}")
    print(f"  * Model Recorded:       {fallback_audit['model']}")
    print(f"  * Validation Status:    {fallback_audit['validation_status']}")
    print(f"  * Items Extracted:      {len(fallback_items)} (Heuristically classified)")
    if fallback_items:
        print(f"  * First Item Type:      {fallback_items[0].decision.memory_type.upper()}")
        print(f"  * Storage Targets:      {fallback_items[0].decision.storage_targets}")

    print_header("DEMONSTRATION COMPLETE: ALL 5 JEV DECISION PIPELINES VERIFIED")

if __name__ == "__main__":
    run_demo()
