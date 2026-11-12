import json
import uuid
import logging
from typing import Dict, Any, Optional
from core.adapters.postgres import PostgresAdapter
from core.graph.sync import GraphSynchronizer
from core.adapters.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)

class OutboxProcessor:
    """Processes pending transactional outbox events for asynchronous derived store sync."""

    def __init__(
        self,
        postgres_adapter: Optional[PostgresAdapter] = None,
        graph_synchronizer: Optional[GraphSynchronizer] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None
    ):
        self.pg = postgres_adapter or PostgresAdapter()
        self.graph = graph_synchronizer or GraphSynchronizer()
        self.embedder = embedding_generator or EmbeddingGenerator()

    def enqueue_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        event_id: Optional[str] = None
    ) -> str:
        eid = event_id or str(uuid.uuid4())
        sql = """
            INSERT INTO outbox_events (id, event_type, payload, status, retry_count, created_at, updated_at)
            VALUES (%s, %s, %s, 'pending', 0, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING;
        """
        self.pg.execute_query(sql, (eid, event_type, json.dumps(payload)))
        return eid

    def process_pending_events(self, limit: int = 50) -> int:
        fetch_sql = """
            SELECT id, event_type, payload, retry_count
            FROM outbox_events
            WHERE status = 'pending' AND retry_count < 5
            ORDER BY created_at ASC
            LIMIT %s;
        """
        events = self.pg.execute_query(fetch_sql, (limit,))
        processed_count = 0

        for event in events:
            eid = event["id"]
            etype = event["event_type"]
            payload = event["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)

            try:
                if etype == "sync_graph":
                    self.graph.sync_memory_relationship(
                        memory_id=payload["memory_id"],
                        subject=payload["subject"],
                        predicate=payload["predicate"],
                        object_entity=payload["object"],
                        epistemic_state=payload.get("epistemic_state", "asserted")
                    )
                elif etype == "sync_vector":
                    mem_id = payload["memory_id"]
                    text = payload["text"]
                    vector = self.embedder.generate_embedding(text)
                    vector_str = f"[{','.join(map(str, vector))}]"
                    update_sql = "UPDATE memories SET embedding = %s::vector WHERE id = %s;"
                    self.pg.execute_query(update_sql, (vector_str, mem_id))

                # Mark completed
                self.pg.execute_query(
                    "UPDATE outbox_events SET status = 'completed', updated_at = NOW() WHERE id = %s;",
                    (eid,)
                )
                processed_count += 1
            except Exception as e:
                logger.error(f"Failed processing outbox event {eid}: {e}")
                self.pg.execute_query(
                    """
                    UPDATE outbox_events 
                    SET retry_count = retry_count + 1, last_error = %s, updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (str(e), eid)
                )

        return processed_count

