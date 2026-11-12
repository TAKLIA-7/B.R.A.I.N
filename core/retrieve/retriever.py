import re
from typing import Dict, Any, List, Optional
from core.adapters.postgres import PostgresAdapter
from core.adapters.neo4j_adapter import Neo4jAdapter
from core.adapters.embeddings import EmbeddingGenerator
from core.retrieve.intent import QueryIntentAnalyzer
from core.retrieve.ranking import MultiFactorRanker
from core.retrieve.context_budget import ContextBudgetManager, RetrievedItem

STOP_WORDS = {
    "what", "does", "which", "this", "that", "with", "from",
    "have", "about", "your", "mine", "ours", "them", "they", "here", "there"
}

class HybridRetriever:
    """
    Coordinates semantic retrieval in PostgreSQL/pgvector, graph traversal in Neo4j,
    bug intelligence lookups, multi-factor ranking, and token-budget constrained context packaging.
    """

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        neo4j_adapter: Optional[Neo4jAdapter] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.neo = neo4j_adapter or Neo4jAdapter()
        self.embedder = embedding_generator or EmbeddingGenerator()
        self.intent_analyzer = QueryIntentAnalyzer()
        self.ranker = MultiFactorRanker()
        self.budget_manager = ContextBudgetManager()

    def search(
        self,
        query: str,
        token_budget: int = 500,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main retrieval entrypoint.
        Understands intent, queries pgvector, checks Neo4j if useful, checks bug history,
        ranks results, respects token budget, and abstains when evidence is insufficient.
        """
        intent = self.intent_analyzer.analyze(query)

        # 1. Semantic pgvector search
        query_vec = self.embedder.generate_embedding(query)
        vec_str = f"[{','.join(map(str, query_vec))}]"

        sql = """
            SELECT 
                m.id, m.type, m.text, m.status, m.epistemic_state, m.source_id, m.created_at,
                s.actor AS source_actor, s.type AS source_type, s.trust_level,
                (m.embedding <=> %s::vector) AS distance
            FROM memories m
            LEFT JOIN sources s ON m.source_id = s.id
            WHERE m.status = 'active' AND m.embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT 15;
        """
        raw_rows = self.pg.execute_query(sql, (vec_str,))

        scored_items: List[RetrievedItem] = []
        for row in raw_rows:
            dist = float(row["distance"]) if row.get("distance") is not None else 1.0
            # Allow vectors with positive similarity (cosine distance < 0.96)
            if dist < 0.96:
                scored_item = self.ranker.score_memory(row, raw_distance=dist)
                scored_items.append(scored_item)

        scored_items.sort(key=lambda x: x.score, reverse=True)

        # 2. Graph retrieval if relationship intent detected
        graph_relationships: Optional[List[Dict[str, Any]]] = None
        if intent.is_graph:
            # Extract query tokens excluding generic stop words
            tokens = [
                t.lower() for t in re.findall(r"\b\w+\b", query)
                if len(t) > 2 and t.lower() not in STOP_WORDS
            ]
            if tokens:
                terms = tokens[:5]
                cypher = """
                    MATCH (s:Entity)-[r]->(o:Entity)
                    WHERE any(t IN $terms WHERE toLower(s.name) CONTAINS t OR toLower(o.name) CONTAINS t)
                    RETURN s.name AS subject, type(r) AS predicate, o.name AS object, 
                           r.epistemic_state AS state, r.canonical_memory_id AS memory_id
                    LIMIT 10
                """
                records = self.neo.execute_cypher(cypher, {"terms": terms})
                if records:
                    graph_relationships = records

        # 3. Bug intelligence retrieval if bug keywords or file paths present
        bug_history: Optional[List[Dict[str, Any]]] = None
        if intent.has_bug_keywords or intent.extracted_symbols:
            bug_sql = """
                SELECT bug_id, title, symptom, root_cause, status, severity, location, reported_by, epistemic_state
                FROM bugs
                ORDER BY first_seen DESC
                LIMIT 5;
            """
            bug_rows = self.pg.execute_query(bug_sql)
            if bug_rows:
                bug_history = bug_rows

        # 4. Context packaging with token budget enforcement and abstention check
        response = self.budget_manager.format_search_response(
            items=scored_items,
            token_budget=token_budget,
            min_score_threshold=0.30,
            graph_relationships=graph_relationships,
            bug_history=bug_history
        )

        return response
