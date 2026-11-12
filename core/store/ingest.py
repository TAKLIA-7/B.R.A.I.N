import uuid
from typing import Dict, Any, List, Optional
from core.models.ingest import IngestRequest, IngestResponse
from core.models.memory import EpistemicState, MemoryStatus
from core.store.extractor import MemoryExtractor
from core.store.provenance import ProvenanceManager
from core.router.router import DeterministicRouter, StorageDestination
from core.store.outbox import OutboxProcessor
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter

class IngestionCoordinator:
    """Coordinates receiving incoming data, deterministic routing, outbox sync, and storage."""

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        extractor: Optional[MemoryExtractor] = None,
        router: Optional[DeterministicRouter] = None,
        outbox_processor: Optional[OutboxProcessor] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.extractor = extractor or MemoryExtractor()
        self.provenance = ProvenanceManager()
        self.router = router or DeterministicRouter()
        self.outbox = outbox_processor or OutboxProcessor(postgres_adapter=self.pg)
        self.redis = RedisAdapter()

    def process_ingestion(self, request: IngestRequest) -> IngestResponse:
        source_id = str(uuid.uuid4())

        # 1. Store canonical source attribution record in PostgreSQL first
        insert_source_sql = """
            INSERT INTO sources (id, type, actor, trust_level, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            RETURNING id, type, actor, trust_level, created_at;
        """
        self.pg.execute_query(
            insert_source_sql,
            (source_id, request.source.type.value, request.source.actor, request.source.trust_level)
        )

        # 2. Extract memory candidates
        candidates = self.extractor.extract_candidates(request)

        # 3. Apply deterministic router and store canonical memories
        stored_memories: List[Dict[str, Any]] = []
        insert_memory_sql = """
            INSERT INTO memories (
                id, type, subject, predicate, object, text,
                status, epistemic_state, source_id, message_ref,
                valid_from, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING id, type, text, status, epistemic_state, source_id;
        """

        for cand in candidates:
            mem_id = str(uuid.uuid4())
            epistemic_state = self.provenance.determine_initial_epistemic_state(cand, request.source)
            status = MemoryStatus.ACTIVE

            # Route deterministically
            decision = self.router.route(cand, request.source, is_temporary=False)

            # Canonical PostgreSQL write
            rows = self.pg.execute_query(
                insert_memory_sql,
                (
                    mem_id,
                    cand.type.value,
                    cand.subject,
                    cand.predicate,
                    cand.object,
                    cand.text,
                    status.value,
                    epistemic_state.value,
                    source_id,
                    cand.message_ref
                )
            )
            if rows:
                stored_memories.append(rows[0])

            # Enqueue derived index synchronization via transactional outbox
            if StorageDestination.PGVECTOR in decision.destinations:
                self.outbox.enqueue_event("sync_vector", {
                    "memory_id": mem_id,
                    "text": cand.text
                })

            if StorageDestination.NEO4J in decision.destinations and cand.subject and cand.predicate and cand.object:
                self.outbox.enqueue_event("sync_graph", {
                    "memory_id": mem_id,
                    "subject": cand.subject,
                    "predicate": cand.predicate,
                    "object": cand.object,
                    "epistemic_state": epistemic_state.value
                })

            if StorageDestination.REDIS in decision.destinations:
                self.redis.set_with_ttl(f"memory:cache:{mem_id}", cand.text, ttl_seconds=decision.ttl_seconds)

        # Process pending outbox events to synchronize pgvector & Neo4j
        self.outbox.process_pending_events()

        return IngestResponse(
            status="success",
            source_id=source_id,
            memories=stored_memories
        )
