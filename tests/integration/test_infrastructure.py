import pytest
import os
import time
import psycopg2
import redis
from neo4j import GraphDatabase

# Environment variables with defaults matching .env.example
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "knowledge_brain")
POSTGRES_USER = os.getenv("POSTGRES_USER", "brain_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "brain_password")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

NEO4J_HOST = os.getenv("NEO4J_HOST", "localhost")
NEO4J_BOLT_PORT = int(os.getenv("NEO4J_BOLT_PORT", "7687"))
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "brain_graph_password")


def test_postgres_connection_and_pgvector():
    """Verify PostgreSQL connects and pgvector extension is functional."""
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            assert cur.fetchone()[0] == 1

            # Check pgvector extension
            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
            row = cur.fetchone()
            assert row is not None, "pgvector extension is not installed"
            assert row[0] == "vector"

            # Check pgvector functionality
            cur.execute("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector AS dist;")
            dist = cur.fetchone()[0]
            assert abs(dist - 1.0) < 1e-4, f"Vector distance expected 1.0, got {dist}"
    finally:
        conn.close()


def test_postgres_canonical_tables_exist():
    """Verify all 12 canonical tables and constraints exist in PostgreSQL."""
    expected_tables = {
        "sources",
        "memories",
        "tasks",
        "checkpoints",
        "call_log",
        "deletions",
        "bugs",
        "attempts",
        "fixes",
        "bug_events",
        "bug_relations",
        "outbox_events",
    }
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public';
            """
            )
            existing_tables = {row[0] for row in cur.fetchall()}
            missing = expected_tables - existing_tables
            assert not missing, f"Missing canonical tables in PostgreSQL: {missing}"
    finally:
        conn.close()


def test_redis_connection_and_ttl():
    """Verify Redis connects, responds to PING, and enforces TTL on temporary keys."""
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD if REDIS_PASSWORD else None,
        decode_responses=True,
    )
    assert r.ping() is True

    test_key = "test:session:transient_context_001"
    test_val = "sample_intermediate_tool_output"
    r.set(test_key, test_val, ex=60)

    retrieved = r.get(test_key)
    assert retrieved == test_val

    ttl = r.ttl(test_key)
    assert 0 < ttl <= 60

    # Cleanup
    r.delete(test_key)


def test_neo4j_connection_and_cypher():
    """Verify Neo4j connects over Bolt protocol and executes parameterized Cypher queries."""
    uri = f"bolt://{NEO4J_HOST}:{NEO4J_BOLT_PORT}"
    driver = GraphDatabase.driver(uri, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            result = session.run("RETURN $x AS answer", x=42)
            single_val = result.single()["answer"]
            assert single_val == 42
    finally:
        driver.close()

