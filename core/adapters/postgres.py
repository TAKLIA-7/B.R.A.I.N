import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List, Dict, Any
from core.config import settings

class PostgresAdapter:
    """PostgreSQL adapter providing connection management and query execution."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None,
                 dbname: Optional[str] = None, user: Optional[str] = None,
                 password: Optional[str] = None):
        self.host = host or settings.POSTGRES_HOST
        self.port = port or settings.POSTGRES_PORT
        self.dbname = dbname or settings.POSTGRES_DB
        self.user = user or settings.POSTGRES_USER
        self.password = password or settings.POSTGRES_PASSWORD

    def get_connection(self):
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password
        )

    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                if cur.description:
                    return [dict(row) for row in cur.fetchall()]
                conn.commit()
                return []

    def execute_script(self, script_path: str) -> None:
        with open(script_path, "r", encoding="utf-8") as f:
            sql = f.read()
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()

    def check_health(self) -> bool:
        try:
            res = self.execute_query("SELECT 1 AS ok;")
            return len(res) == 1 and res[0]["ok"] == 1
        except Exception:
            return False

    def is_pgvector_installed(self) -> bool:
        try:
            res = self.execute_query("SELECT extname FROM pg_extension WHERE extname = 'vector';")
            return len(res) == 1 and res[0]["extname"] == "vector"
        except Exception:
            return False

