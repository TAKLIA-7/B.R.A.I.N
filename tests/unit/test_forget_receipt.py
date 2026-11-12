import pytest
from core.forget.forget_manager import DeletionReceipt, BACKUP_LIMITATION_NOTICE

def test_deletion_receipt_structure():
    receipt = DeletionReceipt(
        receipt_id="rec-001",
        scope="memory_id:mem-123",
        status="completed",
        affected_systems=["postgres", "pgvector", "redis", "neo4j", "markdown"],
        verification={
            "direct_check": "passed",
            "semantic_check": "passed",
            "graph_check": "passed",
            "redis_check": "passed"
        },
        records_invalidated=1,
        backup_policy_notice=BACKUP_LIMITATION_NOTICE
    )
    assert receipt.status == "completed"
    assert "postgres" in receipt.affected_systems
    assert receipt.verification["semantic_check"] == "passed"
    assert "backup" in receipt.backup_policy_notice.lower()

def test_partial_failure_receipt():
    receipt = DeletionReceipt(
        receipt_id="rec-002",
        scope="actor:alice",
        status="partial_failure",
        affected_systems=["postgres", "pgvector"],
        verification={
            "direct_check": "passed",
            "semantic_check": "passed",
            "graph_check": "failed_connection"
        },
        records_invalidated=2,
        backup_policy_notice=BACKUP_LIMITATION_NOTICE
    )
    assert receipt.status == "partial_failure"
    assert receipt.verification["graph_check"] == "failed_connection"

