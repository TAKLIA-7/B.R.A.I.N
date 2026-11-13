"""
core/conflict/detector.py
Identifies conflicting candidate memories and requirements against incoming claims.
Maps potential impacts to project Markdown documents.
"""
import re
import logging
from typing import Dict, Any, List, Optional
from core.adapters.postgres import PostgresAdapter

logger = logging.getLogger(__name__)

DOCUMENT_KEYWORD_MAP = {
    "architecture/database_design.md": ["database", "postgres", "redis", "neo4j", "mongodb", "mysql", "sqlite", "table", "schema", "column", "migration"],
    "architecture/system_architecture.md": ["architecture", "framework", "fastapi", "django", "express", "layer", "orchestration", "router", "service"],
    "architecture/infrastructure.md": ["infrastructure", "docker", "port", "cluster", "host", "container", "deploy", "server", "aws", "gcp"],
    "technical/security.md": ["security", "auth", "authentication", "authorization", "jwt", "oauth", "token", "encryption", "cipher", "secret", "ssl", "tls", "key"],
    "technical/api_conventions.md": ["api", "endpoint", "rest", "graphql", "http", "route", "json", "status code", "payload"],
    "technical/coding_standards.md": ["convention", "style", "formatting", "pep8", "linter", "type hint", "naming", "standard"]
}

OPPOSING_CONCEPT_PAIRS = [
    ("postgresql", "mongodb"),
    ("postgres", "mysql"),
    ("jwt", "session cookie"),
    ("jwt", "session"),
    ("rs256", "hs256"),
    ("fastapi", "django"),
    ("fastapi", "flask"),
    ("redis", "memcached"),
    ("neo4j", "arangodb"),
    ("rest", "graphql")
]

CHANGE_VERBS = [
    "migrate", "switch", "replace", "change", "disable", "instead of",
    "supersede", "no longer", "update", "deprecate", "drop", "remove", "tentatively"
]


class ConflictDetector:
    """Detects contradiction candidates in PostgreSQL memories and requirements."""

    def __init__(self, postgres_adapter: Optional[PostgresAdapter] = None):
        self.pg = postgres_adapter or PostgresAdapter()

    def find_candidate_memories(self, incoming_claim: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Finds active memories that share entities, concepts, or opposing technologies with claim."""
        claim_lower = incoming_claim.lower()
        candidates: List[Dict[str, Any]] = []

        # 1. Check opposing concept pairs
        opposing_terms: List[str] = []
        for term_a, term_b in OPPOSING_CONCEPT_PAIRS:
            if term_a in claim_lower:
                opposing_terms.append(term_b)
            if term_b in claim_lower:
                opposing_terms.append(term_a)

        has_change_verb = any(v in claim_lower for v in CHANGE_VERBS)

        # If neither opposing terms nor change verbs are present, it is not a candidate conflict
        if not opposing_terms and not has_change_verb:
            return []

        search_terms = list(opposing_terms)
        if has_change_verb:
            for doc_path, kw_list in DOCUMENT_KEYWORD_MAP.items():
                for kw in kw_list:
                    if kw in claim_lower and kw not in search_terms:
                        search_terms.append(kw)

        if not search_terms:
            return []

        # Query PostgreSQL active memories
        try:
            query = """
                SELECT id, type, subject, predicate, object, text,
                       epistemic_state, source_id, created_at
                FROM memories
                WHERE status = 'active'
                  AND (
            """
            conds = []
            params = []
            for term in search_terms[:8]:
                conds.append("text ILIKE %s")
                params.append(f"%{term}%")
            query += " OR ".join(conds) + ") ORDER BY created_at DESC LIMIT %s;"
            params.append(limit)

            rows = self.pg.execute_query(query, tuple(params))
            candidates.extend(rows)
        except Exception as e:
            logger.debug(f"Error searching candidate memories: {e}")

        return candidates

    def find_conflicting_requirements(self, incoming_claim: str, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Finds approved requirements that may be contradicted by incoming claim."""
        claim_lower = incoming_claim.lower()
        has_change_verb = any(v in claim_lower for v in CHANGE_VERBS)
        opposing_terms: List[str] = []
        for term_a, term_b in OPPOSING_CONCEPT_PAIRS:
            if term_a in claim_lower:
                opposing_terms.append(term_b)
            if term_b in claim_lower:
                opposing_terms.append(term_a)

        if not has_change_verb and not opposing_terms:
            return []

        words = [w for w in re.findall(r"\b[a-zA-Z]{4,}\b", claim_lower) if w not in ["with", "from", "that", "this", "have", "will"]]
        if not words:
            return []

        try:
            query = """
                SELECT r.id, r.req_id, r.title, r.module, r.category, r.current_version,
                       rv.description
                FROM requirements r
                JOIN requirement_versions rv ON r.id = rv.requirement_id AND r.current_version = rv.version
                WHERE r.status = 'approved'
            """
            params: List[Any] = []
            if project_id:
                query += " AND r.project_id = %s"
                params.append(project_id)

            query += " AND ("
            conds = []
            for w in words[:5]:
                conds.append("r.title ILIKE %s OR rv.description ILIKE %s")
                params.extend([f"%{w}%", f"%{w}%"])
            query += " OR ".join(conds) + ") LIMIT 5;"

            rows = self.pg.execute_query(query, tuple(params))
            return rows
        except Exception as e:
            logger.debug(f"Error searching conflicting requirements: {e}")
            return []

    @staticmethod
    def identify_affected_documents(claim: str) -> List[str]:
        """Maps claim content to affected project Markdown documentation paths."""
        claim_lower = claim.lower()
        affected: List[str] = []
        for doc_path, keywords in DOCUMENT_KEYWORD_MAP.items():
            if any(re.search(r"\b" + re.escape(kw) + r"\b", claim_lower) for kw in keywords):
                affected.append(doc_path)
        return affected or ["architecture/system_architecture.md"]

