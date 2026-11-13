"""
core/conflict/rules.py
Deterministic Python rules for mandatory human approval of knowledge conflicts.
Enforces that LLM confidence scores NEVER bypass or override mandatory human approval.
"""
import re
from typing import Dict, Any, List, Optional, Tuple

RULE_AMBIGUOUS_INSTRUCTION = "RULE_01_AMBIGUOUS_INSTRUCTION"
RULE_INSUFFICIENT_EVIDENCE = "RULE_02_INSUFFICIENT_EVIDENCE"
RULE_UNSPECIFIED_TIMING = "RULE_03_UNSPECIFIED_TIMING"
RULE_REQUIREMENT_CONTRADICTION = "RULE_04_REQUIREMENT_CONTRADICTION"
RULE_CRITICAL_ARCHITECTURE_IMPACT = "RULE_05_CRITICAL_ARCHITECTURE_IMPACT"
RULE_UNRELIABLE_JEV_RESOLUTION = "RULE_06_UNRELIABLE_JEV_RESOLUTION"
RULE_MISSING_TARGET_STATE = "RULE_07_MISSING_TARGET_STATE"

AMBIGUOUS_KEYWORDS = [
    "maybe", "might", "perhaps", "probably", "consider",
    "tentatively", "unclear", "not sure", "possibly", "could be",
    "seems like", "potentially", "subject to change", "hypothetically"
]

UNSPECIFIED_TIMING_KEYWORDS = [
    "will migrate", "planning to", "in progress", "wip",
    "thinking of", "scheduled to", "will use in future", "eventually",
    "drafting", "under consideration", "someday", "soon"
]

CRITICAL_DOMAIN_KEYWORDS = [
    "database", "postgres", "redis", "neo4j", "mongodb", "mysql", "sqlite",
    "jwt", "oauth", "auth", "authentication", "authorization", "encryption",
    "cipher", "secret", "ssl", "tls", "security", "framework", "architecture",
    "port", "cluster", "infrastructure", "docker", "fastapi", "django"
]


class MandatoryApprovalEvaluator:
    """
    Evaluates deterministic Python rules to determine whether a conflict must
    pause and require mandatory human-in-the-loop approval.
    """

    @staticmethod
    def evaluate(
        incoming_claim: str,
        existing_memories: List[Dict[str, Any]],
        conflicting_requirements: List[Dict[str, Any]],
        evidence_and_provenance: Optional[Dict[str, Any]] = None,
        jev_proposed_resolution: str = "dispute",
        new_trust_level: float = 0.5,
        jev_confidence: float = 0.5
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Returns:
            (requires_human_approval, triggered_rule_ids, reasons)
        """
        claim_lower = incoming_claim.lower()
        triggered_rules: List[str] = []
        reasons: List[str] = []

        evidence = evidence_and_provenance or {}

        # Rule 1: Ambiguous Instruction
        for kw in AMBIGUOUS_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", claim_lower):
                triggered_rules.append(RULE_AMBIGUOUS_INSTRUCTION)
                reasons.append(f"Incoming instruction contains ambiguous phrasing: '{kw}'")
                break

        # Rule 3: Unspecified Timing (Planned / WIP vs Completed)
        for kw in UNSPECIFIED_TIMING_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", claim_lower):
                triggered_rules.append(RULE_UNSPECIFIED_TIMING)
                reasons.append(f"Unclear whether modification is planned, in progress, or completed: '{kw}'")
                break

        # Rule 4: Conflicts with an approved requirement
        if conflicting_requirements:
            req_ids = [r.get("req_id", "REQ") for r in conflicting_requirements]
            triggered_rules.append(RULE_REQUIREMENT_CONTRADICTION)
            reasons.append(f"Claim contradicts approved project requirement(s): {', '.join(req_ids)}")

        # Rule 5: Critical Architecture, Database, Security, or Infrastructure impact
        for kw in CRITICAL_DOMAIN_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", claim_lower):
                triggered_rules.append(RULE_CRITICAL_ARCHITECTURE_IMPACT)
                reasons.append(f"Claim affects critical architecture, database, security, or infra domain: '{kw}'")
                break

        # Rule 2: Contradiction without sufficient evidence
        has_empirical_proof = bool(
            evidence.get("test_results") or
            evidence.get("verification_proof") or
            evidence.get("commit_sha") or
            evidence.get("passed_tests")
        )
        if not has_empirical_proof and existing_memories:
            # Check trust level of existing memories
            max_existing_trust = max(
                [float(m.get("trust_level", m.get("trust_score", 0.5))) for m in existing_memories] or [0.5]
            )
            # If trust delta is small (< 0.3) and no test evidence, require human approval
            if (new_trust_level - max_existing_trust) < 0.3:
                triggered_rules.append(RULE_INSUFFICIENT_EVIDENCE)
                reasons.append("Contradicts existing active knowledge without automated test evidence or sufficient trust delta")

        # Rule 6: JEV cannot reliably distinguish resolution
        if jev_proposed_resolution in ["dispute", "reject"] and existing_memories:
            if RULE_UNRELIABLE_JEV_RESOLUTION not in triggered_rules:
                triggered_rules.append(RULE_UNRELIABLE_JEV_RESOLUTION)
                reasons.append(f"JEV resolution is '{jev_proposed_resolution}'; requires explicit human arbitration")
        elif jev_confidence < 0.85 and existing_memories:
            if RULE_UNRELIABLE_JEV_RESOLUTION not in triggered_rules:
                triggered_rules.append(RULE_UNRELIABLE_JEV_RESOLUTION)
                reasons.append(f"JEV decision confidence ({jev_confidence:.2f}) is below reliable threshold (0.85)")

        # Rule 7: Available evidence does not establish the intended new state
        if len(incoming_claim.strip()) < 15 or not any(c.isalpha() for c in incoming_claim):
            triggered_rules.append(RULE_MISSING_TARGET_STATE)
            reasons.append("Claim is too terse or vague to establish the intended canonical state")

        requires_approval = len(triggered_rules) > 0
        return requires_approval, triggered_rules, reasons

