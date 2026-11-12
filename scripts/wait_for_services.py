import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.adapters.postgres import PostgresAdapter
from core.adapters.redis_adapter import RedisAdapter
from core.adapters.neo4j_adapter import Neo4jAdapter

def wait_for_services(timeout=60):
    start = time.time()
    print("[*] Waiting for PostgreSQL, Redis, and Neo4j to become ready...")
    
    pg = PostgresAdapter()
    rd = RedisAdapter()
    n4 = Neo4jAdapter()

    pg_ready = False
    rd_ready = False
    n4_ready = False

    while time.time() - start < timeout:
        if not pg_ready and pg.check_health():
            pg_ready = True
            print("  [+] PostgreSQL is READY.")
        if not rd_ready and rd.ping():
            rd_ready = True
            print("  [+] Redis is READY.")
        if not n4_ready and n4.check_health():
            n4_ready = True
            print("  [+] Neo4j is READY.")

        if pg_ready and rd_ready and n4_ready:
            print("[+] All services are READY and reachable!")
            return True
        time.sleep(2)

    print(f"[-] Timed out after {timeout} seconds. State: PG={pg_ready}, Redis={rd_ready}, Neo4j={n4_ready}")
    return False

def apply_migrations():
    migration_file = os.path.join(os.path.dirname(__file__), "..", "migrations", "001_initial_schema.sql")
    print(f"[*] Applying migration: {migration_file}")
    pg = PostgresAdapter()
    pg.execute_script(migration_file)
    print("[+] Migration 001 applied successfully!")

if __name__ == "__main__":
    if not wait_for_services():
        sys.exit(1)
    apply_migrations()

