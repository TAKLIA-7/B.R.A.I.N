from neo4j import GraphDatabase, Driver
from typing import Optional, List, Dict, Any
from core.config import settings

class Neo4jAdapter:
    """Neo4j adapter for derived knowledge graph operations with parameterized Cypher."""

    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        self.uri = uri or settings.neo4j_bolt_uri
        self.user = user or settings.NEO4J_USER
        self.password = password or settings.NEO4J_PASSWORD
        self._driver: Optional[Driver] = None

    @property
    def driver(self) -> Driver:
        if self._driver is None:
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        return self._driver

    def check_health(self) -> bool:
        try:
            self.driver.verify_connectivity()
            with self.driver.session() as session:
                res = session.run("RETURN 1 AS ok")
                record = res.single()
                return record is not None and record["ok"] == 1
        except Exception:
            return False

    def execute_cypher(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def close(self):
        if self._driver is not None:
            self._driver.close()
            self._driver = None

