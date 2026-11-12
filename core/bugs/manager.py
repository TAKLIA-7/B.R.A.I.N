import json
import uuid
from typing import Dict, Any, List, Optional
from core.adapters.postgres import PostgresAdapter

class BugManager:
    """Core manager for structured defect records, attempts, fixes, relationships, and history."""

    def __init__(self, postgres_adapter: Optional[PostgresAdapter] = None):
        self.pg = postgres_adapter or PostgresAdapter()

    def evaluate_fix_status(self, verification: Dict[str, Any], human_approval: bool = False) -> str:
        """
        Verification Gate:
        A fix can NEVER be marked 'verified' merely because an agent claims so.
        Verification strictly requires passing test proof or explicit human sign-off.
        """
        if human_approval:
            return "verified"

        if isinstance(verification, dict):
            res = verification.get("result", "").lower()
            code = verification.get("test_exit_code")
            if res in ("passed", "success") or code == 0:
                return "verified"

        return "fixed"

    def detect_relationship(
        self,
        signature: Optional[str],
        location: Optional[Dict[str, Any]],
        existing_bugs: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, str]]:
        """Detects whether a reported defect is a duplicate of an open bug or a regression of a verified fix."""
        if not signature:
            return None

        bugs = existing_bugs
        if bugs is None:
            bugs = self.pg.execute_query("SELECT bug_id, signature, status, location FROM bugs WHERE signature IS NOT NULL;")

        for b in bugs:
            if b.get("signature") == signature:
                if b.get("status") in ("verified", "fixed"):
                    return {
                        "relation_type": "regression_of",
                        "target_bug_id": b["bug_id"],
                        "reason": f"Matches signature of previously resolved bug {b['bug_id']}"
                    }
                elif b.get("status") in ("open", "investigating"):
                    return {
                        "relation_type": "duplicate_of",
                        "target_bug_id": b["bug_id"],
                        "reason": f"Matches signature of active bug {b['bug_id']}"
                    }
        return None

    def report_bug(
        self,
        bug_id: str,
        title: str,
        symptom: str,
        root_cause: Optional[str] = None,
        severity: str = "medium",
        location: Optional[Dict[str, Any]] = None,
        signature: Optional[str] = None,
        reported_by: str = "agent"
    ) -> Dict[str, Any]:
        # Check for duplicate or regression relationships
        relation = self.detect_relationship(signature, location)

        sql = """
            INSERT INTO bugs (bug_id, title, symptom, root_cause, status, severity, location, signature, first_seen, reported_by, epistemic_state)
            VALUES (%s, %s, %s, %s, 'open', %s, %s::jsonb, %s, NOW(), %s, 'asserted')
            ON CONFLICT (bug_id) DO UPDATE SET title = EXCLUDED.title, symptom = EXCLUDED.symptom
            RETURNING bug_id, title, status, severity, reported_by;
        """
        loc_json = json.dumps(location or {})
        rows = self.pg.execute_query(sql, (bug_id, title, symptom, root_cause, severity, loc_json, signature, reported_by))
        
        # Log event in append-only bug_events
        self.log_event(bug_id, "reported", None, "open", reported_by, "Initial bug report")

        # Record relation if detected
        if relation:
            rel_sql = """
                INSERT INTO bug_relations (bug_id, related_bug_id, relation_type, created_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (bug_id, related_bug_id, relation_type) DO NOTHING;
            """
            self.pg.execute_query(rel_sql, (bug_id, relation["target_bug_id"], relation["relation_type"]))

        return rows[0]

    def log_attempt(
        self,
        bug_id: str,
        agent: str,
        hypothesis: str,
        action: str,
        outcome: str,
        evidence: Optional[Dict[str, Any]] = None,
        learned: Optional[str] = None
    ) -> Dict[str, Any]:
        attempt_id = str(uuid.uuid4())
        sql = """
            INSERT INTO attempts (attempt_id, bug_id, agent, hypothesis, action, outcome, evidence, learned, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW())
            RETURNING attempt_id, bug_id, agent, outcome, created_at;
        """
        rows = self.pg.execute_query(sql, (attempt_id, bug_id, agent, hypothesis, action, outcome, json.dumps(evidence or {}), learned))
        
        # Transition to investigating if currently open
        self.pg.execute_query("UPDATE bugs SET status = 'investigating' WHERE bug_id = %s AND status = 'open';", (bug_id,))
        self.log_event(bug_id, "attempt_logged", "open", "investigating", agent, f"Attempt [{outcome.upper()}]: {hypothesis}")
        return rows[0]

    def record_fix(
        self,
        fix_id: str,
        bug_id: str,
        commit: Optional[str],
        files_changed: List[str],
        summary: str,
        verification: Dict[str, Any],
        fixed_by: str,
        supersedes_fix: Optional[str] = None,
        human_approval: bool = False
    ) -> Dict[str, Any]:
        # Determine verified status via verification gate
        new_status = self.evaluate_fix_status(verification, human_approval=human_approval)

        sql = """
            INSERT INTO fixes (fix_id, bug_id, commit, files_changed, summary, verification, fixed_by, supersedes_fix, created_at)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s, NOW())
            ON CONFLICT (fix_id) DO UPDATE SET summary = EXCLUDED.summary
            RETURNING fix_id, bug_id, fixed_by, created_at;
        """
        rows = self.pg.execute_query(sql, (
            fix_id, bug_id, commit, json.dumps(files_changed), summary,
            json.dumps(verification), fixed_by, supersedes_fix
        ))

        # Update bug status and epistemic state
        new_epistemic = "confirmed" if new_status == "verified" else "asserted"
        self.pg.execute_query(
            "UPDATE bugs SET status = %s, epistemic_state = %s WHERE bug_id = %s;",
            (new_status, new_epistemic, bug_id)
        )
        self.log_event(bug_id, "fix_recorded", "investigating", new_status, fixed_by, summary)
        return rows[0]

    def log_event(self, bug_id: str, event: str, from_status: Optional[str], to_status: Optional[str], agent: str, reason: str) -> None:
        """Appends an event to the append-only bug_events table."""
        sql = """
            INSERT INTO bug_events (bug_id, event, from_status, to_status, agent, reason, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, NOW());
        """
        self.pg.execute_query(sql, (bug_id, event, from_status, to_status, agent, reason))

    def search_bugs(self, query: str) -> List[Dict[str, Any]]:
        sql = """
            SELECT bug_id, title, symptom, root_cause, status, severity, location, signature, reported_by, epistemic_state
            FROM bugs
            WHERE title ILIKE %s OR symptom ILIKE %s OR signature ILIKE %s OR location::text ILIKE %s
            ORDER BY first_seen DESC
            LIMIT 10;
        """
        param = f"%{query}%"
        return self.pg.execute_query(sql, (param, param, param, param))

    def get_bug_history(self, bug_id: str) -> Dict[str, Any]:
        bug_rows = self.pg.execute_query("SELECT * FROM bugs WHERE bug_id = %s;", (bug_id,))
        if not bug_rows:
            return {"status": "not_found", "message": f"Bug {bug_id} not found"}

        attempts = self.pg.execute_query("SELECT * FROM attempts WHERE bug_id = %s ORDER BY created_at ASC;", (bug_id,))
        fixes = self.pg.execute_query("SELECT * FROM fixes WHERE bug_id = %s ORDER BY created_at ASC;", (bug_id,))
        events = self.pg.execute_query("SELECT * FROM bug_events WHERE bug_id = %s ORDER BY timestamp ASC;", (bug_id,))
        relations = self.pg.execute_query("SELECT * FROM bug_relations WHERE bug_id = %s OR related_bug_id = %s;", (bug_id, bug_id))

        return {
            "bug": bug_rows[0],
            "attempts": attempts,
            "fixes": fixes,
            "events": events,
            "relations": relations
        }
