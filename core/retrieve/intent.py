import re
from typing import Set
from pydantic import BaseModel

class QueryIntent(BaseModel):
    is_semantic: bool = True
    is_graph: bool = False
    has_bug_keywords: bool = False
    extracted_symbols: Set[str] = set()

class QueryIntentAnalyzer:
    """Analyzes search query intent to determine which indexes (pgvector, Neo4j, PostgreSQL bugs) to consult."""

    GRAPH_KEYWORDS = {
        "relationship", "relates", "connected", "connect", "connects",
        "uses", "use", "using", "used", "depends", "depend", "depends_on",
        "hierarchy", "developed", "develops", "who", "what", "which",
        "architecture", "entity", "component", "links", "linked"
    }

    BUG_KEYWORDS = {
        "bug", "error", "exception", "failure", "traceback", "fix",
        "crash", "defect", "reproduce", "symptom", "failed", "attempt"
    }

    def analyze(self, query: str) -> QueryIntent:
        q_lower = query.lower()
        words = set(re.findall(r"\b\w+\b", q_lower))

        is_graph = bool(words & self.GRAPH_KEYWORDS)
        has_bug = bool(words & self.BUG_KEYWORDS) or any(
            ext in q_lower for ext in [".py", ".js", ".ts", "bug-", "fix-", "def ", "class "]
        )

        # Extract file paths or symbol names
        symbols = set(re.findall(r"[\w/\\-]+\.(?:py|json|md|sql)", query))

        return QueryIntent(
            is_semantic=True,
            is_graph=is_graph,
            has_bug_keywords=has_bug,
            extracted_symbols=symbols
        )
