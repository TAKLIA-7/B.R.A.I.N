import re
from typing import List, Dict, Any
from core.jev.contracts import (
    MemoryDecision,
    IngestionAnalysisItem,
    RetrievalDecision,
    HandoverDecision,
    ConflictDecision
)

class DeterministicJEVFallback:
    """
    Deterministic rule-based fallback engine used when JEV is disabled or OpenRouter is unreachable.
    Guarantees that Knowledge Brain operations continue safely while explicitly flagging fallback usage.
    """

    def evaluate_ingestion(
        self,
        text: str,
        source_type: str = "agent",
        trust_level: float = 0.8
    ) -> List[IngestionAnalysisItem]:
        items: List[IngestionAnalysisItem] = []
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        for line in lines:
            lower = line.lower()
            # 1. Temporary context
            if any(k in lower for k in ["temp:", "scratch:", "debug:", "intermediate:"]):
                decision = MemoryDecision(
                    memory_type="procedure",
                    lifetime="temporary",
                    importance=0.3,
                    confidence=0.8,
                    scope="session",
                    storage_targets=["redis"],
                    requires_semantic_search=False,
                    has_meaningful_relationships=False,
                    requires_confirmation=False,
                    epistemic_assessment="asserted",
                    reasoning="Deterministic fallback routed temporary debug line to Redis"
                )
                items.append(IngestionAnalysisItem(text=line, decision=decision))
                continue

            # 2. Decisions
            if any(k in lower for k in ["decided", "decision", "chose", "selected", "will use"]):
                decision = MemoryDecision(
                    memory_type="decision",
                    lifetime="persistent",
                    importance=0.9,
                    confidence=0.95,
                    scope="architecture",
                    storage_targets=["postgres", "pgvector", "neo4j", "obsidian"],
                    requires_semantic_search=True,
                    has_meaningful_relationships=True,
                    requires_confirmation=False,
                    epistemic_assessment="confirmed" if trust_level >= 0.85 else "asserted",
                    reasoning="Deterministic fallback identified explicit architectural decision"
                )
                items.append(IngestionAnalysisItem(
                    text=line,
                    subject="System",
                    predicate="decided",
                    object=line,
                    decision=decision
                ))
                continue

            # 3. Tasks
            if any(k in lower for k in ["task:", "todo:", "implement", "build", "refactor"]):
                decision = MemoryDecision(
                    memory_type="task",
                    lifetime="persistent",
                    importance=0.75,
                    confidence=0.9,
                    scope="project",
                    storage_targets=["postgres", "redis", "obsidian"],
                    requires_semantic_search=True,
                    has_meaningful_relationships=False,
                    requires_confirmation=False,
                    epistemic_assessment="asserted",
                    reasoning="Deterministic fallback identified actionable task"
                )
                items.append(IngestionAnalysisItem(text=line, decision=decision))
                continue

            # 4. Preferences
            if any(k in lower for k in ["prefer", "format", "style", "convention"]):
                decision = MemoryDecision(
                    memory_type="preference",
                    lifetime="persistent",
                    importance=0.7,
                    confidence=0.85,
                    scope="user",
                    storage_targets=["postgres", "pgvector"],
                    requires_semantic_search=True,
                    has_meaningful_relationships=False,
                    requires_confirmation=False,
                    epistemic_assessment="asserted",
                    reasoning="Deterministic fallback identified user or coding preference"
                )
                items.append(IngestionAnalysisItem(text=line, decision=decision))
                continue

            # 5. Default: Fact
            decision = MemoryDecision(
                memory_type="fact",
                lifetime="persistent",
                importance=0.6,
                confidence=0.85,
                scope="general",
                storage_targets=["postgres", "pgvector", "obsidian"],
                requires_semantic_search=True,
                has_meaningful_relationships=False,
                requires_confirmation=False,
                epistemic_assessment="confirmed" if trust_level >= 0.9 else "asserted",
                reasoning="Deterministic fallback identified factual statement"
            )
            items.append(IngestionAnalysisItem(text=line, decision=decision))

        return items

    def evaluate_retrieval(
        self,
        query: str,
        token_budget: int = 500,
        candidates: List[Dict[str, Any]] = None
    ) -> RetrievalDecision:
        lower = query.lower()
        is_graph = any(k in lower for k in ["relat", "connect", "depend", "graph", "who", "which component"])
        strategy = "hybrid" if is_graph else "semantic"

        selected_ids = []
        if candidates:
            # Sort by distance or score
            sorted_cand = sorted(candidates, key=lambda c: c.get("score", 0.0), reverse=True)
            for c in sorted_cand[:10]:
                mid = c.get("id") or c.get("memory_id")
                if mid:
                    selected_ids.append(str(mid))

        return RetrievalDecision(
            retrieval_strategy=strategy,
            include_semantic_search=True,
            include_keyword_search=False,
            include_graph_search=is_graph,
            selected_memory_ids=selected_ids,
            priority_memory_types=["decision", "fact", "preference"],
            token_budget=token_budget,
            abstain=False,
            reasoning=f"Deterministic fallback configured {strategy} retrieval strategy"
        )

    def evaluate_handover(
        self,
        task_id: str,
        checkpoint_id: str,
        bugs: List[str],
        fixes: List[str],
        memory_ids: List[str],
        unresolved_questions: List[str],
        token_budget: int = 1000
    ) -> HandoverDecision:
        return HandoverDecision(
            task_id=task_id,
            selected_checkpoint_id=checkpoint_id,
            relevant_memory_ids=memory_ids[:5],
            relevant_bug_ids=bugs[:5],
            relevant_fix_ids=fixes[:5],
            unresolved_questions=unresolved_questions,
            token_budget=token_budget,
            reasoning="Deterministic fallback assembled compact handover context without transcripts"
        )

    def evaluate_conflict(
        self,
        existing_memory: Dict[str, Any],
        new_claim: str,
        new_trust_level: float
    ) -> ConflictDecision:
        existing_trust = float(existing_memory.get("trust_score", 0.5))
        mid = str(existing_memory.get("memory_id") or existing_memory.get("id"))

        if new_trust_level > existing_trust + 0.2:
            resolution = "supersede"
            assigned_state = "confirmed" if new_trust_level >= 0.85 else "asserted"
            reason = "New claim has significantly higher trust score than existing claim"
        elif abs(new_trust_level - existing_trust) <= 0.2:
            resolution = "dispute"
            assigned_state = "disputed"
            reason = "Claims from equally trusted sources conflict; marked disputed pending verification"
        else:
            resolution = "reject"
            assigned_state = "asserted"
            reason = "New claim trust is lower than existing confirmed claim"

        return ConflictDecision(
            conflict_detected=True,
            conflicting_memory_id=mid,
            resolution=resolution,
            assigned_epistemic_state=assigned_state,
            reasoning=reason
        )

