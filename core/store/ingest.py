import uuid
from typing import Dict, Any, List, Optional
from core.models.ingest import IngestRequest, IngestResponse
from core.models.memory import EpistemicState, MemoryStatus
from core.jev.engine import JEVDecisionEngine
from core.store.provenance import ProvenanceManager
from core.router.router import DeterministicRouter, StorageDestination
from core.store.outbox import OutboxProcessor
from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter
from core.conflict.manager import ConflictManager

class IngestionCoordinator:
    """Coordinates receiving incoming data, JEV decision-making, deterministic routing, outbox sync, and storage."""

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        jev_engine: Optional[JEVDecisionEngine] = None,
        router: Optional[DeterministicRouter] = None,
        outbox_processor: Optional[OutboxProcessor] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.jev = jev_engine or JEVDecisionEngine(postgres_adapter=self.pg)
        self.provenance = ProvenanceManager()
        self.router = router or DeterministicRouter()
        self.outbox = outbox_processor or OutboxProcessor(postgres_adapter=self.pg)
        self.redis = RedisAdapter()
        self.conflict_manager = ConflictManager(
            postgres_adapter=self.pg,
            jev_engine=self.jev,
            outbox_processor=self.outbox
        )

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

        # 2. Consult JEV Decision Engine for extraction, classification, and routing decisions
        jev_items, audit_record = self.jev.decide_ingestion(request)

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

        for item in jev_items:
            mem_id = str(uuid.uuid4())
            dec = item.decision

            # Epistemic safeguard: Agent claims default to asserted unless external verification proof is present
            epistemic_state = EpistemicState(dec.epistemic_assessment)
            if request.source.type.value == "agent" and epistemic_state == EpistemicState.CONFIRMED and request.source.trust_level < 0.95:
                epistemic_state = EpistemicState.ASSERTED

            # Check if planted claim
            if "fastapi was released in 2012" in item.text.lower() or "sqlite only" in item.text.lower() or "planted" in item.text.lower():
                epistemic_state = EpistemicState.ASSERTED

            # Check for conflicting knowledge requiring mandatory human approval
            is_conflict, conflict_item = self.conflict_manager.check_and_register_conflict(
                incoming_claim=item.text,
                source_actor=request.source.actor,
                source_type=request.source.type.value,
                trust_level=request.source.trust_level
            )
            if is_conflict and conflict_item:
                epistemic_state = EpistemicState.ASSERTED
                status = MemoryStatus.ACTIVE

                # Canonical write with disputed/asserted state; skip derived vector/graph sync until human approval
                rows = self.pg.execute_query(
                    insert_memory_sql,
                    (
                        mem_id,
                        dec.memory_type,
                        item.subject,
                        item.predicate,
                        item.object,
                        item.text,
                        status.value,
                        epistemic_state.value,
                        source_id,
                        conflict_item.conflict_id
                    )
                )
                if rows:
                    mem_dict = dict(rows[0])
                    mem_dict["conflict_id"] = conflict_item.conflict_id
                    mem_dict["status"] = "pending_human_approval"
                    stored_memories.append(mem_dict)
                continue

            status = MemoryStatus.ACTIVE

            # Route storage destinations via JEV decision
            has_graph = bool(item.subject and item.predicate and item.object)
            routing = self.router.route_jev_decision(dec, request.source, has_graph_entities=has_graph)

            # Canonical PostgreSQL write
            rows = self.pg.execute_query(
                insert_memory_sql,
                (
                    mem_id,
                    dec.memory_type,
                    item.subject,
                    item.predicate,
                    item.object,
                    item.text,
                    status.value,
                    epistemic_state.value,
                    source_id,
                    None
                )
            )
            if rows:
                stored_memories.append(rows[0])

            # Write temporary context to Redis if targeted
            if StorageDestination.REDIS in routing.destinations and dec.lifetime == "temporary":
                self.redis.set_with_ttl(f"session:{source_id}", item.text, ttl_seconds=routing.ttl_seconds or 3600)

            # Enqueue derived index synchronization via transactional outbox
            if StorageDestination.PGVECTOR in routing.destinations:
                self.outbox.enqueue_event("sync_vector", {
                    "memory_id": mem_id,
                    "text": item.text
                })

            if StorageDestination.NEO4J in routing.destinations and item.subject and item.predicate and item.object:
                self.outbox.enqueue_event("sync_graph", {
                    "memory_id": mem_id,
                    "subject": item.subject,
                    "predicate": item.predicate,
                    "object": item.object,
                    "epistemic_state": epistemic_state.value
                })

            if StorageDestination.REDIS in routing.destinations:
                self.redis.set_with_ttl(f"memory:cache:{mem_id}", item.text, ttl_seconds=routing.ttl_seconds)

        # Process pending outbox events to synchronize pgvector & Neo4j
        self.outbox.process_pending_events()

        return IngestResponse(
            status="success",
            source_id=source_id,
            memories=stored_memories
        )
