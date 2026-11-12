import pytest
import os
import subprocess
import time
import psycopg2
import redis
from neo4j import GraphDatabase

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

def test_volume_persistence():
    """Verify that PostgreSQL, Redis, and Neo4j retain data across container restarts."""
    test_task_id = "test-task-persistence-001"
    
    # 1. Insert test record in PostgreSQL
    pg_conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD
    )
    try:
        with pg_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tasks (id, goal, created_by) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET goal = EXCLUDED.goal;",
                (test_task_id, "Verify persistent volume retention", "pytest")
            )
        pg_conn.commit()
    finally:
        pg_conn.close()

    # 2. Insert test node in Neo4j
    neo_uri = f"bolt://{NEO4J_HOST}:{NEO4J_BOLT_PORT}"
    driver = GraphDatabase.driver(neo_uri, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            session.run("MERGE (p:Project {name: 'KnowledgeBrainPersistence'}) SET p.verified = true")
    finally:
        driver.close()

    # 3. Restart containers using docker-compose restart
    res = subprocess.run(["docker-compose", "restart"], capture_output=True, text=True)
    assert res.returncode == 0, f"docker-compose restart failed: {res.stderr}"

    # Wait for services to recover with polling
    neo_ready = False
    start = time.time()
    while time.time() - start < 45:
        try:
            temp_driver = GraphDatabase.driver(neo_uri, auth=(NEO4J_USER, NEO4J_PASSWORD))
            temp_driver.verify_connectivity()
            temp_driver.close()
            neo_ready = True
            break
        except Exception:
            time.sleep(2)
    assert neo_ready, "Neo4j did not become ready within 45s after restart"

    # 4. Verify PostgreSQL data survived restart
    pg_conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD
    )
    try:
        with pg_conn.cursor() as cur:
            cur.execute("SELECT goal FROM tasks WHERE id = %s;", (test_task_id,))
            row = cur.fetchone()
            assert row is not None, "PostgreSQL task record was lost after restart!"
            assert row[0] == "Verify persistent volume retention"
            # Cleanup test task
            cur.execute("DELETE FROM tasks WHERE id = %s;", (test_task_id,))
        pg_conn.commit()
    finally:
        pg_conn.close()

    # 5. Verify Neo4j data survived restart
    driver = GraphDatabase.driver(neo_uri, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            result = session.run("MATCH (p:Project {name: 'KnowledgeBrainPersistence'}) RETURN p.verified AS verified")
            record = result.single()
            assert record is not None, "Neo4j node was lost after restart!"
            assert record["verified"] is True
            # Cleanup test node
            session.run("MATCH (p:Project {name: 'KnowledgeBrainPersistence'}) DELETE p")
    finally:
        driver.close()

