import json
import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Tuple
from core.config import settings
from core.adapters.postgres import PostgresAdapter
from core.jev.contracts import (
    MemoryDecision,
    IngestionAnalysisItem,
    RetrievalDecision,
    HandoverDecision,
    ConflictDecision
)
from core.jev.client import OpenRouterJEVClient, JEVRequestError
from core.jev.fallback import DeterministicJEVFallback
from core.models.ingest import IngestRequest

logger = logging.getLogger(__name__)

INGESTION_SYSTEM_PROMPT = """
You are JEV (Judge & Evaluation Validator), the central memory decision engine for Knowledge Brain.
Analyze the provided content and return a JSON object with a list of extracted items and storage decisions.
Strict Schema:
{
  "items": [
    {
      "text": "normalized statement",
      "subject": "entity or null",
      "predicate": "relation or null",
      "object": "target or null",
      "decision": {
        "memory_type": "fact" | "preference" | "decision" | "task" | "experience" | "procedure",
        "lifetime": "temporary" | "persistent",
        "importance": float (0.0 to 1.0),
        "confidence": float (0.0 to 1.0),
        "scope": "architecture" | "project" | "user" | "session" | "general",
        "storage_targets": ["postgres" | "redis" | "pgvector" | "neo4j" | "obsidian"],
        "requires_semantic_search": boolean,
        "has_meaningful_relationships": boolean,
        "requires_confirmation": boolean,
        "epistemic_assessment": "asserted" | "confirmed" | "disputed",
        "reasoning": "concise explanation"
      }
    }
  ]
}
Guidelines:
- Temporary scratchpad, debug info, intermediate steps -> lifetime "temporary", storage_targets ["redis"].
- Persistent facts/decisions -> lifetime "persistent", storage_targets ["postgres", "pgvector"].
- Entities with clear subject-predicate-object -> include "neo4j".
- Important decisions -> include "obsidian".
- Agent claims without external evidence must have epistemic_assessment "asserted".
Return ONLY valid JSON.
"""

RETRIEVAL_SYSTEM_PROMPT = """
You are JEV, the central memory retrieval decision engine for Knowledge Brain.
Determine the optimal retrieval strategy and token allocation for the agent query.
Strict Schema:
{
  "retrieval_strategy": "semantic" | "graph" | "hybrid" | "keyword",
  "include_semantic_search": boolean,
  "include_keyword_search": boolean,
  "include_graph_search": boolean,
  "selected_memory_ids": ["string ids of relevant memories from candidate list"],
  "priority_memory_types": ["decision", "fact", etc.],
  "token_budget": integer,
  "abstain": boolean,
  "reasoning": "concise explanation"
}
Guidelines:
- If query is about relationships/dependencies, enable graph search.
- If query has no supporting evidence in candidates, set abstain true.
Return ONLY valid JSON.
"""

HANDOVER_SYSTEM_PROMPT = """
You are JEV, the cross-agent handover decision engine for Knowledge Brain.
Select the minimal, most actionable context for an incoming fresh agent resuming an unfinished task.
Do NOT transfer conversational chatter or raw transcripts.
Strict Schema:
{
  "task_id": "string",
  "selected_checkpoint_id": "string",
  "relevant_memory_ids": ["string ids"],
  "relevant_bug_ids": ["string ids"],
  "relevant_fix_ids": ["string ids"],
  "unresolved_questions": ["string questions"],
  "token_budget": integer,
  "reasoning": "concise explanation"
}
Return ONLY valid JSON.
"""

CONFLICT_SYSTEM_PROMPT = """
You are JEV, the conflict resolution decision engine for Knowledge Brain.
Compare an existing stored memory with a newly proposed claim and determine resolution.
Strict Schema:
{
  "conflict_detected": boolean,
  "conflicting_memory_id": "string id or null",
  "resolution": "supersede" | "dispute" | "coexist" | "reject",
  "assigned_epistemic_state": "asserted" | "confirmed" | "disputed",
  "reasoning": "concise explanation"
}
Return ONLY valid JSON.
"""

class JEVDecisionEngine:
    """
    Central intelligent decision engine for Knowledge Brain.
    Uses OpenRouter as the model gateway for inference while Python validates contracts
    and executes deterministic operations.
    """

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        client: Optional[OpenRouterJEVClient] = None,
        fallback: Optional[DeterministicJEVFallback] = None,
        enabled: Optional[bool] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.enabled = enabled if enabled is not None else settings.JEV_ENABLED
        self.client = client or OpenRouterJEVClient()
        self.fallback = fallback or DeterministicJEVFallback()

    def _log_decision_audit(
        self,
        decision_id: str,
        operation_type: str,
        agent: str,
        model: str,
        provider: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: float,
        decision_json: Dict[str, Any],
        validation_status: str,
        fallback_used: bool
    ) -> Dict[str, Any]:
        """Writes append-only audit record to jev_decisions table in PostgreSQL."""
        record = {
            "decision_id": decision_id,
            "operation_type": operation_type,
            "agent": agent,
            "model": model,
            "provider": provider,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": round(latency_ms, 2),
            "decision_json": decision_json,
            "validation_status": validation_status,
            "fallback_used": fallback_used
        }

        try:
            sql = """
                INSERT INTO jev_decisions (
                    decision_id, operation_type, agent, model, provider,
                    tokens_in, tokens_out, latency_ms, decision_json,
                    validation_status, fallback_used, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW());
            """
            self.pg.execute_query(sql, (
                decision_id,
                operation_type,
                agent,
                model,
                provider,
                tokens_in,
                tokens_out,
                latency_ms,
                json.dumps(decision_json),
                validation_status,
                fallback_used
            ))
        except Exception as e:
            logger.error(f"Failed to write JEV decision audit record: {e}", exc_info=True)

        return record

    def _combine_request_text(self, request: IngestRequest) -> str:
        parts = []
        if request.content:
            parts.append(request.content)
        if request.messages:
            for m in request.messages:
                parts.append(f"{m.role}: {m.content}")
        if request.document:
            title = f"Document '{request.document.title}': " if request.document.title else "Document: "
            parts.append(f"{title}{request.document.content}")
        if request.tool_output:
            parts.append(f"Tool '{request.tool_output.tool_name}' output: {request.tool_output.output}")
        return "\n".join(parts)

    def decide_ingestion(self, request: IngestRequest) -> Tuple[List[IngestionAnalysisItem], Dict[str, Any]]:
        """
        Determines memory categories, lifetime, importance, epistemic state, and storage routing.
        """
        start = time.monotonic()
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        agent = request.source.actor
        combined_text = self._combine_request_text(request)

        fallback_used = False
        items: List[IngestionAnalysisItem] = []
        tokens_in, tokens_out = 0, 0
        model_name = self.client.model
        provider_name = "openrouter"

        if self.enabled and self.client.api_key:
            try:
                user_prompt = f"Source Type: {request.source.type.value}\nAuthor: {agent}\nTrust: {request.source.trust_level}\nContent:\n{combined_text}"
                resp = self.client.invoke_json(INGESTION_SYSTEM_PROMPT, user_prompt)
                tokens_in = resp.prompt_tokens
                tokens_out = resp.completion_tokens
                model_name = resp.model

                raw_items = resp.content.get("items", [])
                for raw in raw_items:
                    # Validate strictly with Pydantic
                    item = IngestionAnalysisItem(**raw)
                    items.append(item)
            except Exception as e:
                logger.warning(f"JEV ingestion call failed: {e}. Engaging deterministic fallback.")
                fallback_used = True
        else:
            fallback_used = True

        if fallback_used:
            provider_name = "deterministic_fallback"
            items = self.fallback.evaluate_ingestion(
                text=combined_text,
                source_type=request.source.type.value,
                trust_level=request.source.trust_level
            )

        latency_ms = (time.monotonic() - start) * 1000
        decision_payload = {"items": [item.model_dump() for item in items]}

        audit = self._log_decision_audit(
            decision_id=decision_id,
            operation_type="ingest",
            agent=agent,
            model=model_name,
            provider=provider_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            decision_json=decision_payload,
            validation_status="passed",
            fallback_used=fallback_used
        )

        return items, audit

    def decide_retrieval(
        self,
        query: str,
        token_budget: int = 500,
        candidates: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[RetrievalDecision, Dict[str, Any]]:
        """
        Determines retrieval strategy, semantic vs graph search, and memory filtering.
        """
        start = time.monotonic()
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        fallback_used = False
        decision = None
        tokens_in, tokens_out = 0, 0
        model_name = self.client.model
        provider_name = "openrouter"

        if self.enabled and self.client.api_key:
            try:
                cand_summary = []
                if candidates:
                    for c in candidates[:15]:
                        cand_summary.append({
                            "id": str(c.get("id") or c.get("memory_id")),
                            "text": c.get("text") or c.get("content"),
                            "type": c.get("type") or c.get("memory_type"),
                            "distance": c.get("distance")
                        })
                user_prompt = f"Query: {query}\nToken Budget: {token_budget}\nCandidate Memories:\n{json.dumps(cand_summary)}"
                resp = self.client.invoke_json(RETRIEVAL_SYSTEM_PROMPT, user_prompt)
                tokens_in = resp.prompt_tokens
                tokens_out = resp.completion_tokens
                model_name = resp.model

                # Validate with Pydantic
                decision = RetrievalDecision(**resp.content)
            except Exception as e:
                logger.warning(f"JEV retrieval call failed: {e}. Engaging deterministic fallback.")
                fallback_used = True
        else:
            fallback_used = True

        if fallback_used:
            provider_name = "deterministic_fallback"
            decision = self.fallback.evaluate_retrieval(
                query=query,
                token_budget=token_budget,
                candidates=candidates
            )

        latency_ms = (time.monotonic() - start) * 1000

        audit = self._log_decision_audit(
            decision_id=decision_id,
            operation_type="retrieve",
            agent="retriever",
            model=model_name,
            provider=provider_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            decision_json=decision.model_dump(),
            validation_status="passed",
            fallback_used=fallback_used
        )

        return decision, audit

    def decide_handover(
        self,
        task_id: str,
        token_budget: int = 1000
    ) -> Tuple[HandoverDecision, Dict[str, Any]]:
        """
        Intelligently selects the latest checkpoint, decisions, bugs, and fixes for cross-agent handover.
        """
        start = time.monotonic()
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        fallback_used = False
        decision = None
        tokens_in, tokens_out = 0, 0
        model_name = self.client.model
        provider_name = "openrouter"

        # Load canonical task and checkpoint from PostgreSQL
        checkpoint_id = "cp-v1"
        bugs_list: List[str] = []
        fixes_list: List[str] = []
        memory_ids: List[str] = []

        try:
            with self.pg.get_connection() as conn:
                with conn.cursor() as cur:
                    # Latest checkpoint
                    cur.execute("""
                        SELECT id, version, state_json, written_by
                        FROM checkpoints
                        WHERE task_id = %s
                        ORDER BY version DESC LIMIT 1;
                    """, (task_id,))
                    row = cur.fetchone()
                    if row:
                        checkpoint_id = f"cp-v{row[1]}"

                    # Recent bugs & fixes
                    cur.execute("SELECT bug_id FROM bugs ORDER BY first_seen DESC LIMIT 5;")
                    bugs_list = [r[0] for r in cur.fetchall()]

                    cur.execute("SELECT fix_id FROM fixes ORDER BY created_at DESC LIMIT 5;")
                    fixes_list = [r[0] for r in cur.fetchall()]

                    # Recent active memories
                    cur.execute("SELECT id FROM memories WHERE status = 'active' ORDER BY created_at DESC LIMIT 5;")
                    memory_ids = [str(r[0]) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"Error querying state for JEV handover: {e}")

        if self.enabled and self.client.api_key:
            try:
                user_prompt = f"Task ID: {task_id}\nCheckpoint: {checkpoint_id}\nCandidate Memories: {memory_ids}\nBugs: {bugs_list}\nFixes: {fixes_list}\nToken Budget: {token_budget}"
                resp = self.client.invoke_json(HANDOVER_SYSTEM_PROMPT, user_prompt)
                tokens_in = resp.prompt_tokens
                tokens_out = resp.completion_tokens
                model_name = resp.model

                decision = HandoverDecision(**resp.content)
            except Exception as e:
                logger.warning(f"JEV handover call failed: {e}. Engaging deterministic fallback.")
                fallback_used = True
        else:
            fallback_used = True

        if fallback_used:
            provider_name = "deterministic_fallback"
            decision = self.fallback.evaluate_handover(
                task_id=task_id,
                checkpoint_id=checkpoint_id,
                bugs=bugs_list,
                fixes=fixes_list,
                memory_ids=memory_ids,
                unresolved_questions=[],
                token_budget=token_budget
            )

        latency_ms = (time.monotonic() - start) * 1000

        audit = self._log_decision_audit(
            decision_id=decision_id,
            operation_type="handover",
            agent="handover_coordinator",
            model=model_name,
            provider=provider_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            decision_json=decision.model_dump(),
            validation_status="passed",
            fallback_used=fallback_used
        )

        return decision, audit

    def decide_conflict(
        self,
        existing_memory: Dict[str, Any],
        new_claim: str,
        new_trust_level: float
    ) -> Tuple[ConflictDecision, Dict[str, Any]]:
        """
        Determines whether a proposed claim conflicts with an existing memory and chooses resolution.
        """
        start = time.monotonic()
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        fallback_used = False
        decision = None
        tokens_in, tokens_out = 0, 0
        model_name = self.client.model
        provider_name = "openrouter"

        if self.enabled and self.client.api_key:
            try:
                user_prompt = f"Existing Memory:\n{json.dumps(existing_memory, default=str)}\n\nNew Claim: {new_claim}\nNew Trust Level: {new_trust_level}"
                resp = self.client.invoke_json(CONFLICT_SYSTEM_PROMPT, user_prompt)
                tokens_in = resp.prompt_tokens
                tokens_out = resp.completion_tokens
                model_name = resp.model

                decision = ConflictDecision(**resp.content)
            except Exception as e:
                logger.warning(f"JEV conflict call failed: {e}. Engaging deterministic fallback.")
                fallback_used = True
        else:
            fallback_used = True

        if fallback_used:
            provider_name = "deterministic_fallback"
            decision = self.fallback.evaluate_conflict(
                existing_memory=existing_memory,
                new_claim=new_claim,
                new_trust_level=new_trust_level
            )

        latency_ms = (time.monotonic() - start) * 1000

        audit = self._log_decision_audit(
            decision_id=decision_id,
            operation_type="conflict",
            agent="conflict_manager",
            model=model_name,
            provider=provider_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            decision_json=decision.model_dump(),
            validation_status="passed",
            fallback_used=fallback_used
        )

        return decision, audit
