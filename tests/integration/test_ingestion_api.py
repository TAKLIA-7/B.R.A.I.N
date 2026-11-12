import pytest
from fastapi.testclient import TestClient
from api import app
from core.adapters.postgres import PostgresAdapter

client = TestClient(app)

def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["postgres"] is True

def test_ingest_conversation_creates_source_and_memories():
    payload = {
        "source": {
            "type": "agent",
            "actor": "antigravity-agent",
            "trust_level": 0.8
        },
        "messages": [
            {
                "role": "user",
                "content": "We need to build a FastAPI Task Management REST API."
            },
            {
                "role": "assistant",
                "content": "Understood. I have decided to structure tasks with PostgreSQL and Pydantic validation."
            }
        ]
    }
    response = client.post("/ingest", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert "source_id" in res_data
    assert len(res_data["memories"]) >= 1

    source_id = res_data["source_id"]

    # Verify directly in PostgreSQL
    pg = PostgresAdapter()
    sources = pg.execute_query("SELECT * FROM sources WHERE id = %s;", (source_id,))
    assert len(sources) == 1
    assert sources[0]["actor"] == "antigravity-agent"
    assert sources[0]["type"] == "agent"

    memories = pg.execute_query("SELECT * FROM memories WHERE source_id = %s;", (source_id,))
    assert len(memories) >= 1
    for m in memories:
        # Agent claims must default to asserted
        assert m["epistemic_state"] == "asserted"
        assert m["status"] == "active"
        assert m["source_id"] == source_id

def test_ingest_planted_claim_remains_asserted():
    payload = {
        "source": {
            "type": "document",
            "actor": "unverified_blog_post",
            "trust_level": 0.2
        },
        "document": {
            "title": "Untrusted Note",
            "content": "PLANTED FALSE CLAIM: Knowledge Brain runs on SQLite only."
        }
    }
    response = client.post("/ingest", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    source_id = res_data["source_id"]

    pg = PostgresAdapter()
    memories = pg.execute_query("SELECT * FROM memories WHERE source_id = %s;", (source_id,))
    assert len(memories) >= 1
    for m in memories:
        assert m["epistemic_state"] == "asserted"
        assert m["epistemic_state"] != "confirmed"

def test_ingest_rejects_malformed_payload():
    bad_payload = {
        "source": {
            "type": "invalid_source_type",
            "actor": "bot"
        }
    }
    response = client.post("/ingest", json=bad_payload)
    assert response.status_code == 422

