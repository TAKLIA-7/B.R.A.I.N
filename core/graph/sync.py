from typing import Optional, Dict, Any
from core.adapters.neo4j_adapter import Neo4jAdapter

VALID_RELATIONSHIPS = {
    "DEVELOPS", "USES", "HAS_TASK", "DECIDED", "ABOUT",
    "SUPPORTED_BY", "SUPERSEDES", "CONTRADICTS", "DERIVED_FROM", "DEFINES"
}

class GraphSynchronizer:
    """Manages idempotent synchronization of entities and relationships to Neo4j."""

    def __init__(self, neo4j_adapter: Optional[Neo4jAdapter] = None):
        self.neo = neo4j_adapter or Neo4jAdapter()

    def sync_memory_relationship(
        self,
        memory_id: str,
        subject: str,
        predicate: str,
        object_entity: str,
        epistemic_state: str = "asserted"
    ) -> None:
        """
        Creates or merges subject and object entity nodes and establishes a directed relationship
        annotated with canonical PostgreSQL memory ID and epistemic state.
        Uses parameterized Cypher to prevent Cypher injection.
        """
        rel_type = predicate.upper().replace(" ", "_")
        if rel_type not in VALID_RELATIONSHIPS:
            rel_type = "ABOUT"

        cypher = f"""
            MERGE (s:Entity {{name: $subject}})
            MERGE (o:Entity {{name: $object}})
            MERGE (s)-[r:{rel_type} {{canonical_memory_id: $memory_id}}]->(o)
            SET r.epistemic_state = $epistemic_state,
                r.updated_at = timestamp()
        """
        self.neo.execute_cypher(cypher, {
            "subject": subject,
            "object": object_entity,
            "memory_id": memory_id,
            "epistemic_state": epistemic_state
        })

    def delete_memory_references(self, memory_id: str) -> int:
        """Removes relationships referencing the deleted PostgreSQL memory ID."""
        cypher = """
            MATCH ()-[r {canonical_memory_id: $memory_id}]->()
            DELETE r
            RETURN count(r) AS deleted_count
        """
        res = self.neo.execute_cypher(cypher, {"memory_id": memory_id})
        return res[0]["deleted_count"] if res else 0

