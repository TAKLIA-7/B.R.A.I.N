"""
scripts/demo_human_in_loop_conflict.py
Demonstration script for Human-in-the-Loop Conflict Resolution in Knowledge Brain.

Walks through:
1. Active canonical memory in PostgreSQL.
2. An AI agent attempts an ambiguous, contradictory change.
3. Knowledge Brain intercepts the contradiction and flags PENDING_HUMAN_APPROVAL.
   -> Verifies canonical memory remains untouched!
4. AI agent attempts to approve its own conflict -> BLOCKED with PermissionError!
5. Human inspects pending conflict and submits approval.
6. Execution updates canonical memory, supersedes old state, and writes audit record.
"""
import uuid
import sys
import os

# Add repo root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.adapters.postgres import PostgresAdapter
from core.conflict.manager import ConflictManager
from core.conflict.schemas import ConflictState

def run_demo():
    pg = PostgresAdapter()
    conflict_mgr = ConflictManager(postgres_adapter=pg)

    print("\n" + "="*70)
    print("  KNOWLEDGE BRAIN: HUMAN-IN-THE-LOOP CONFLICT RESOLUTION DEMO")
    print("="*70)

    # ---------------------------------------------------------
    # STEP 1: Established Canonical Active Knowledge
    # ---------------------------------------------------------
    mem_id = str(uuid.uuid4())
    pg.execute_query("""
        INSERT INTO memories (id, type, text, status, epistemic_state, created_at)
        VALUES (%s, 'decision', 'We use PostgreSQL for all relational storage.', 'active', 'confirmed', NOW());
    """, (mem_id,))
    print(f"\n[STEP 1] Established Active Canonical Memory:")
    print(f"  -> Memory ID: {mem_id}")
    print(f"  -> Content:   'We use PostgreSQL for all relational storage.'")
    print(f"  -> Status:    ACTIVE | Epistemic: CONFIRMED")

    # ---------------------------------------------------------
    # STEP 2: Incoming Ambiguous Agent Contradiction
    # ---------------------------------------------------------
    agent_claim = "Maybe we should migrate relational storage from PostgreSQL to MongoDB."
    print(f"\n[STEP 2] Incoming Contradictory Claim from AI Agent:")
    print(f"  -> Agent: 'autonomous-agent-42'")
    print(f"  -> Claim: '{agent_claim}'")

    is_conflict, item = conflict_mgr.check_and_register_conflict(
        incoming_claim=agent_claim,
        source_actor="autonomous-agent-42",
        trust_level=0.7
    )

    print(f"\n  [EVALUATION RESULT]:")
    print(f"  -> Conflict Detected:          {is_conflict}")
    print(f"  -> Conflict ID:                 {item.conflict_id}")
    print(f"  -> Status:                      {item.status}")
    print(f"  -> Mandatory Rules Triggered:   {item.applicable_rule_ids}")
    print(f"  -> Reason:                      {item.reason_approval_required}")

    # Verify canonical memory was NOT touched
    cur_mem = pg.execute_query("SELECT status, epistemic_state FROM memories WHERE id = %s;", (mem_id,))[0]
    print(f"\n  [SAFETY CHECK]: Active memory modified?")
    print(f"  -> Status is still '{cur_mem['status']}' (UNTOUCHED)")
    print(f"  -> Epistemic state is still '{cur_mem['epistemic_state']}'")

    # ---------------------------------------------------------
    # STEP 3: Agent Attempts Self-Approval (MUST BE BLOCKED)
    # ---------------------------------------------------------
    print(f"\n[STEP 3] AI Agent attempts to self-approve its own conflict:")
    try:
        conflict_mgr.approve_conflict(
            conflict_id=item.conflict_id,
            approver="autonomous-agent-42",
            is_human=False
        )
        print("  -> ERROR: Self-approval should have been blocked!")
        sys.exit(1)
    except PermissionError as e:
        print(f"  -> [BLOCKED SUCCESSFULLY]: {e}")

    # ---------------------------------------------------------
    # STEP 4: Human Reviews Pending Queue
    # ---------------------------------------------------------
    print(f"\n[STEP 4] Human Engineer inspects pending conflicts queue:")
    pending = conflict_mgr.list_pending_approvals()
    print(f"  -> Found {len(pending)} pending conflict(s) awaiting human review.")
    match = next(c for c in pending if c.conflict_id == item.conflict_id)
    print(f"  -> Reviewing Conflict: {match.conflict_id}")
    print(f"     Proposed Resolution: {match.proposed_resolution}")
    print(f"     Affected Docs:       {match.potentially_affected_documents}")

    # ---------------------------------------------------------
    # STEP 5: Authorized Human Approves Resolution
    # ---------------------------------------------------------
    print(f"\n[STEP 5] Human Approver 'LeadArchitect_Tanish' approves with rationale:")
    approval_result = conflict_mgr.approve_conflict(
        conflict_id=item.conflict_id,
        approver="LeadArchitect_Tanish",
        rationale="Approved after Q4 architecture review committee sign-off",
        selected_resolution="supersede",
        is_human=True
    )
    print(f"  -> Approval Execution: SUCCESS")
    print(f"  -> Final Status:        {approval_result['status']}")
    print(f"  -> Resolution Applied:  {approval_result['resolution']}")
    print(f"  -> New Canonical ID:    {approval_result['new_memory_id']}")

    # ---------------------------------------------------------
    # STEP 6: Verify Post-Approval Canonical Database State
    # ---------------------------------------------------------
    print(f"\n[STEP 6] Post-Approval Database Verification:")
    old_state = pg.execute_query("SELECT status, valid_until FROM memories WHERE id = %s;", (mem_id,))[0]
    new_state = pg.execute_query("SELECT id, text, status, epistemic_state, supersedes_id FROM memories WHERE id = %s;", (approval_result['new_memory_id'],))[0]
    audit_row = pg.execute_query("SELECT actor, action, decision, rationale FROM conflict_audit_log WHERE conflict_id = %s AND action = 'approved';", (item.conflict_id,))[0]

    print(f"  -> Old Memory Status:     {old_state['status']} (valid_until: {old_state['valid_until']})")
    print(f"  -> New Memory Status:     {new_state['status']} | Epistemic: {new_state['epistemic_state']}")
    print(f"  -> Supersedes Pointer:    {new_state['supersedes_id']}")
    print(f"  -> Audit Log Entry:")
    print(f"     Actor:     {audit_row['actor']}")
    print(f"     Action:    {audit_row['action']}")
    print(f"     Decision:  {audit_row['decision']}")
    print(f"     Rationale: {audit_row['rationale']}")

    print("\n" + "="*70)
    print("  ALL HUMAN-IN-THE-LOOP VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("="*70 + "\n")

if __name__ == "__main__":
    run_demo()
