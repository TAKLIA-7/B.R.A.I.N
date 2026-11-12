from datetime import datetime, timezone
from typing import Dict, Any
from core.retrieve.context_budget import RetrievedItem

class MultiFactorRanker:
    """
    Combines semantic similarity (relevance) with source trust level, epistemic state,
    and recency. Relevance acts as the primary gate so that high trust or freshness
    can never elevate an irrelevant memory.
    """

    def __init__(
        self,
        weight_relevance: float = 0.50,
        weight_trust: float = 0.30,
        weight_epistemic: float = 0.15,
        weight_freshness: float = 0.05
    ):
        self.w_rel = weight_relevance
        self.w_trust = weight_trust
        self.w_epi = weight_epistemic
        self.w_fresh = weight_freshness

    def score_memory(self, memory_row: Dict[str, Any], raw_distance: float) -> RetrievedItem:
        # Distance is cosine distance in [0, 2], perfect match is 0.0
        # Convert distance to similarity in [0, 1]
        relevance = max(0.0, min(1.0, 1.0 - raw_distance))

        trust = float(memory_row.get("trust_level") or 0.5)

        epistemic_state = memory_row.get("epistemic_state", "asserted")
        epistemic_weight = 1.0 if epistemic_state == "confirmed" else (0.8 if epistemic_state == "asserted" else 0.4)

        # Freshness calculation
        created_at = memory_row.get("created_at")
        freshness = 1.0
        if created_at and isinstance(created_at, datetime):
            now = datetime.now(timezone.utc)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            hours_old = max(0.0, (now - created_at).total_seconds() / 3600.0)
            freshness = max(0.2, 1.0 / (1.0 + hours_old * 0.01))

        # Gate composite score on relevance: irrelevant memories must remain low scoring
        composite_multiplier = (
            self.w_rel +
            self.w_trust * trust +
            self.w_epi * epistemic_weight +
            self.w_fresh * freshness
        )
        composite_score = relevance * composite_multiplier

        provenance_data = {
            "source_id": str(memory_row.get("source_id")),
            "actor": memory_row.get("source_actor") or "unknown",
            "source_type": memory_row.get("source_type") or "unknown",
            "trust_level": trust
        }

        return RetrievedItem(
            id=str(memory_row.get("id")),
            text=memory_row.get("text", ""),
            score=composite_score,
            epistemic_state=epistemic_state,
            provenance=provenance_data,
            type=memory_row.get("type", "fact")
        )
