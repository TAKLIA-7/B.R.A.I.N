from enum import Enum
from typing import List, Optional
from pydantic import BaseModel
from core.models.memory import ExtractedMemoryCandidate, MemoryType
from core.models.ingest import SourceMetadata, SourceType
from core.config import settings
from core.adapters.redis_adapter import RedisAdapter
from core.jev.contracts import MemoryDecision

class StorageDestination(str, Enum):
    POSTGRES = "postgres"
    REDIS = "redis"
    PGVECTOR = "pgvector"
    NEO4J = "neo4j"

class RoutingDecision(BaseModel):
    destinations: List[StorageDestination]
    ttl_seconds: Optional[int] = None
    reason: str

class DeterministicRouter:
    """
    Evaluates extracted memory candidates and metadata to deterministically decide
    storage destinations across PostgreSQL, Redis, pgvector, and Neo4j.
    """

    def __init__(self, redis_adapter: Optional[RedisAdapter] = None):
        self.redis = redis_adapter or RedisAdapter()
        self.default_ttl = settings.REDIS_DEFAULT_TTL_SECONDS

    def route(
        self,
        candidate: ExtractedMemoryCandidate,
        source: SourceMetadata,
        is_temporary: bool = False
    ) -> RoutingDecision:
        """
        Deterministic application routing logic.
        LLMs never decide storage destinations independently.
        """
        destinations: List[StorageDestination] = []
        ttl: Optional[int] = None

        if is_temporary:
            # Rule 1 & 2: Temporary context, intermediate debug states go to Redis with TTL
            destinations.append(StorageDestination.REDIS)
            ttl = self.default_ttl
            return RoutingDecision(
                destinations=destinations,
                ttl_seconds=ttl,
                reason="Temporary session context or intermediate tool output routed to Redis with TTL"
            )

        # Rule 3: Durable memories must be persisted in canonical PostgreSQL
        destinations.append(StorageDestination.POSTGRES)

        # Rule 4: Resumable task or checkpoint also gets cached in Redis for fast access
        if candidate.resumable or candidate.type == MemoryType.TASK:
            destinations.append(StorageDestination.REDIS)
            ttl = self.default_ttl * 2

        # Rule 5: Eligible memories receive semantic vector embeddings in pgvector
        if candidate.requires_semantic_search:
            destinations.append(StorageDestination.PGVECTOR)

        # Rule 6: Meaningful entity relationships are indexed in Neo4j
        if candidate.has_meaningful_relationships and candidate.subject and candidate.predicate and candidate.object:
            destinations.append(StorageDestination.NEO4J)

        return RoutingDecision(
            destinations=destinations,
            ttl_seconds=ttl,
            reason="Durable canonical record assigned to PostgreSQL with semantic/graph indexing as appropriate"
        )

    def route_jev_decision(
        self,
        decision: MemoryDecision,
        source: SourceMetadata,
        has_graph_entities: bool = False
    ) -> RoutingDecision:
        """
        Executes storage routing directly determined by JEV decision contract.
        Validates target storage systems deterministically.
        """
        destinations: List[StorageDestination] = []
        ttl: Optional[int] = None

        if "redis" in decision.storage_targets:
            destinations.append(StorageDestination.REDIS)
            ttl = self.default_ttl if decision.lifetime == "temporary" else self.default_ttl * 2

        if "postgres" in decision.storage_targets or decision.lifetime == "persistent":
            if StorageDestination.POSTGRES not in destinations:
                destinations.append(StorageDestination.POSTGRES)

        if "pgvector" in decision.storage_targets or decision.requires_semantic_search:
            if StorageDestination.PGVECTOR not in destinations:
                destinations.append(StorageDestination.PGVECTOR)

        if "neo4j" in decision.storage_targets or (decision.has_meaningful_relationships and has_graph_entities):
            if StorageDestination.NEO4J not in destinations:
                destinations.append(StorageDestination.NEO4J)

        return RoutingDecision(
            destinations=destinations,
            ttl_seconds=ttl,
            reason=f"JEV decision routed: {decision.reasoning}"
        )

    def store_temporary_context(self, session_id: str, content: str, ttl_seconds: Optional[int] = None) -> str:
        """Helper to store short-lived session context in Redis."""
        key = f"session:{session_id}"
        ttl = ttl_seconds or self.default_ttl
        self.redis.set_with_ttl(key, content, ttl_seconds=ttl)
        return key

