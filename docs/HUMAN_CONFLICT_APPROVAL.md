# Human-in-the-Loop Conflict Resolution in Knowledge Brain

Knowledge Brain extends the JEV conflict-resolution architecture with an authoritative **Human-in-the-Loop Approval Gate**. Whenever incoming information contradicts existing active knowledge and the intended change is ambiguous, unsupported, or high-impact, Knowledge Brain automatically pauses the proposed update, preserves the active canonical state, and requests explicit human approval before modifying active knowledge.

The system **never** silently replaces, deletes, supersedes, or alters important existing knowledge when the intended change is unclear.

---

## 1. Conflict States & Workflow

```
       Incoming Claim Contradicts Existing Memory / Requirement
                                │
                                ▼
                       ┌─────────────────┐
                       │    detected     │
                       └────────┬────────┘
                                │ Evaluated by JEV + Deterministic Rules
                                ▼
                       ┌─────────────────┐
                       │   evaluating    │
                       └────────┬────────┘
                                │ Mandatory Approval Triggered
                                ▼
                   ┌───────────────────────────┐
                   │  pending_human_approval   │ ◄── Canonical active knowledge is UNCHANGED
                   └───────┬───────────┬───────┘
                           │           │
         Human Rejection   │           │   Human Approval
         ┌─────────────────┘           └─────────────────┐
         ▼                                               ▼
┌──────────────────┐                           ┌──────────────────┐
│     rejected     │                           │     approved     │
│ Active state kept│                           │ Action executed: │
│ No sync to stores│                           │ supersede/coexist│
└──────────────────┘                           └─────────┬────────┘
                                                         │
                                                         ▼
                                               ┌──────────────────┐
                                               │     resolved     │
                                               │ Sync: pgvector,  │
                                               │ Neo4j, Markdown  │
                                               └──────────────────┘
```

The 7 standard conflict states:
1. **`detected`**: Contradiction identified between incoming claim and active memories or approved requirements.
2. **`evaluating`**: JEV and deterministic rules evaluate whether automatic resolution is permitted or human approval is mandatory.
3. **`pending_human_approval`**: Update is paused. Canonical PostgreSQL memories, vector indexes, knowledge graph, and Markdown docs remain **strictly unchanged**.
4. **`clarification_required`**: Additional evidence or instruction is requested. Silence or timeout never implies approval.
5. **`approved`**: An authorized human approver has sanctioned the proposed resolution (or selected an alternative).
6. **`rejected`**: The human approver rejected the change. Canonical knowledge remains active and the rejected claim is never synchronized.
7. **`resolved`**: Approved action has been executed, outbox events processed, and Markdown documentation updated.

---

## 2. Mandatory Approval Conditions (Deterministic Python Rules)

Human approval is required whenever any of these deterministic Python rules trigger:

| Rule ID | Name | Trigger Condition | Rationale |
|---|---|---|---|
| `RULE_01` | `AMBIGUOUS_INSTRUCTION` | Phrasing contains "maybe", "might", "perhaps", "probably", "consider", "tentatively", "unclear". | Ambiguous agent suggestions must not silently mutate production knowledge. |
| `RULE_02` | `INSUFFICIENT_EVIDENCE` | Contradiction without empirical test verification proofs and trust delta $< 0.3$. | Agent claims lacking verifiable evidence cannot override confirmed facts. |
| `RULE_03` | `UNSPECIFIED_TIMING` | Phrasing contains "will migrate", "planning to", "in progress", "wip", "thinking of", "scheduled to". | Prevents premature recording of planned or in-progress work as completed reality. |
| `RULE_04` | `REQUIREMENT_CONTRADICTION` | Contradicts an existing approved project requirement in `requirements` table. | Requirement changes must follow formal evolution approval. |
| `RULE_05` | `CRITICAL_ARCHITECTURE_IMPACT` | Touches database engine, auth protocol (JWT, OAuth), encryption, ports, clustering, or security keys. | High-blast-radius architectural decisions require explicit human sign-off. |
| `RULE_06` | `UNRELIABLE_JEV_RESOLUTION` | JEV resolution is `dispute` or decision confidence is below reliable threshold ($< 0.85$). | Equivocal model judgment must be arbitrated by humans. |
| `RULE_07` | `MISSING_TARGET_STATE` | Claim is terse or vague, failing to establish the intended new state. | Prevents corrupted or partial knowledge ingestion. |

> [!IMPORTANT]
> **Deterministic Rule Guarantee:** LLM confidence scores **never** override mandatory approval rules. If any rule triggers, human arbitration is strictly enforced.

---

## 3. Human Authorization & Agent Self-Approval Ban

- **AI Agents are strictly forbidden from approving their own conflicts.**
- Attempts by agents (`is_human=False` or `approver="agent-..."`) to call approval endpoints immediately raise `PermissionError` (HTTP 403 Forbidden).
- Only verified human operators can approve high-impact knowledge modifications.

---

## 4. Approval Execution & Post-Approval Synchronization

When approval is received from an authorized human:
1. **Optimistic Concurrency Check**: Verifies target memories have not been altered or superseded concurrently since conflict detection.
2. **Canonical State Mutation**:
   - `supersede`: Marks old memory as `status = 'superseded'` (`valid_until = NOW()`), inserts new memory with `status = 'active'`, `epistemic_state = 'confirmed'`, and `supersedes_id = old_id`.
   - `dispute`: Marks existing memory as `epistemic_state = 'disputed'`.
   - `coexist`: Inserts new memory with distinct contextual scope.
   - `reject`: Leaves canonical memory active and untouched.
3. **Derived Storage Synchronization**: Enqueues transactional outbox events to sync `pgvector` embeddings and `Neo4j` relationship graph.
4. **Project Markdown Synchronization**: Uses `ProjectDocumentSynchronizer` to record approved decisions in affected documents (e.g. `architecture/database_design.md`), respecting manual-edit conflict detection.
5. **Audit Logging**: Appends full decision receipt to `conflict_audit_log` and `memory_conflicts` table.

---

## 5. Tool & API Reference

### FastMCP Tools:
- **`memory_conflicts_list(project_id)`**: Lists pending conflicts awaiting human arbitration.
- **`memory_conflict_get(conflict_id)`**: Retrieves full conflict details, rules triggered, evidence, and active snapshot.
- **`memory_conflict_approve(conflict_id, approver, rationale, selected_resolution, is_human=True)`**: Approves conflict resolution (human only).
- **`memory_conflict_reject(conflict_id, approver, rationale, is_human=True)`**: Rejects conflict (human only).
- **`memory_conflict_clarify(conflict_id, author, clarification_notes, updated_claim)`**: Submits clarification and additional evidence.
- **`memory_check_conflict(claim, project_id, source_actor, trust_level)`**: Proactively checks a claim for conflicts before ingestion.

### REST API Endpoints:
- `GET /conflicts/pending`: Lists pending approval requests.
- `GET /conflicts/{conflict_id}`: Retrieves full conflict record.
- `POST /conflicts/{conflict_id}/approve`: Approves a conflict (requires `is_human: true`).
- `POST /conflicts/{conflict_id}/reject`: Rejects a conflict.
- `POST /conflicts/{conflict_id}/clarify`: Submits clarification notes.
- `POST /conflicts/check`: Checks claim against active knowledge.

