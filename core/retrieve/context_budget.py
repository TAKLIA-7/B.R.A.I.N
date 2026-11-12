import math
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field

class RetrievedItem(BaseModel):
    id: str
    text: str
    score: float = Field(default=0.5, ge=0.0, le=1.0)
    epistemic_state: str = "asserted"
    provenance: Any = "unknown"
    type: Optional[str] = "fact"

class ContextBudgetManager:
    """Estimates tokens, enforces caller-supplied token budgets, and formats responses."""

    def __init__(self, chars_per_token_estimate: float = 4.0):
        self.chars_per_token = chars_per_token_estimate

    def estimate_tokens(self, text: str) -> Tuple[int, bool]:
        """
        Conservative token estimation.
        Always returns (token_count, is_estimate) where is_estimate is True
        as specified: 'Never claim exact token counts from character counts'.
        """
        if not text:
            return 0, True
        
        # Word + punctuation approximation
        words = len(text.split())
        char_based = math.ceil(len(text) / self.chars_per_token)
        estimated = max(words, char_based)
        return estimated, True

    def build_compact_context(
        self,
        items: List[RetrievedItem],
        token_budget: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Packs ranked items into the context window until the token budget is reached.
        Preserves provenance and epistemic qualifiers.
        """
        packed_items: List[Dict[str, Any]] = []
        total_tokens = 0

        for item in items:
            item_tokens, _ = self.estimate_tokens(item.text)
            # Add metadata overhead estimate (~10 tokens)
            item_total = item_tokens + 10
            
            if total_tokens + item_total <= token_budget:
                packed_items.append({
                    "id": item.id,
                    "text": item.text,
                    "type": item.type,
                    "epistemic_state": item.epistemic_state,
                    "score": round(item.score, 4),
                    "provenance": item.provenance,
                    "estimated_tokens": item_tokens
                })
                total_tokens += item_total
            else:
                # Budget exhausted
                break

        return packed_items, total_tokens

    def format_search_response(
        self,
        items: List[RetrievedItem],
        token_budget: int,
        min_score_threshold: float = 0.4,
        graph_relationships: Optional[List[Dict[str, Any]]] = None,
        bug_history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Returns structured compact response.
        Abstains with 'no supporting memory' when evidence is weak or insufficient.
        """
        # Filter items meeting minimum confidence/relevance threshold
        filtered_items = [it for it in items if it.score >= min_score_threshold]

        if not filtered_items and not graph_relationships and not bug_history:
            return {
                "abstain": True,
                "message": "no supporting memory",
                "memories": [],
                "token_budget": token_budget,
                "tokens_used": 0,
                "token_count_mode": "conservative_estimate"
            }

        packed_memories, used_tokens = self.build_compact_context(filtered_items, token_budget)

        response: Dict[str, Any] = {
            "abstain": False,
            "memories": packed_memories,
            "token_budget": token_budget,
            "tokens_used": used_tokens,
            "token_count_mode": "conservative_estimate"
        }

        if graph_relationships is not None:
            response["graph_relationships"] = graph_relationships

        if bug_history is not None:
            response["bug_history"] = bug_history

        return response

