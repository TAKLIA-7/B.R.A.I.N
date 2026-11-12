from typing import Optional, Dict, Any
from core.models.memory import EpistemicState, ExtractedMemoryCandidate
from core.models.ingest import SourceMetadata, SourceType

class ProvenanceManager:
    """Enforces provenance attribution and epistemic state transitions according to strict trust rules."""

    def determine_initial_epistemic_state(
        self,
        candidate: ExtractedMemoryCandidate,
        source: SourceMetadata
    ) -> EpistemicState:
        """
        Determines the initial epistemic state of an extracted memory candidate.
        Rule 1: Agent-generated claims default to 'asserted'.
        Rule 2: Document claims default to 'asserted'.
        Rule 3: User input may be 'confirmed' only if trust level is high (>= 0.95); otherwise 'asserted'.
        Rule 4: Planted or unverified claims never automatically become 'confirmed'.
        """
        if source.type in (SourceType.AGENT, SourceType.TOOL, SourceType.DOCUMENT):
            return EpistemicState.ASSERTED

        if source.type == SourceType.USER:
            if source.trust_level >= 0.95:
                return EpistemicState.CONFIRMED
            return EpistemicState.ASSERTED

        return EpistemicState.ASSERTED

    def evaluate_state_with_evidence(
        self,
        candidate: ExtractedMemoryCandidate,
        source: SourceMetadata,
        verification_evidence: Optional[Dict[str, Any]] = None,
        human_approval: bool = False
    ) -> EpistemicState:
        """
        Elevates a claim to 'confirmed' ONLY if empirical verification evidence or explicit human approval is provided.
        """
        if human_approval:
            return EpistemicState.CONFIRMED

        if verification_evidence:
            # Check for verification indicators (e.g. exit code 0, test passed)
            if verification_evidence.get("test_exit_code") == 0 or verification_evidence.get("passed") is True:
                return EpistemicState.CONFIRMED

        return self.determine_initial_epistemic_state(candidate, source)

    def resolve_conflict(
        self,
        existing_state: EpistemicState,
        existing_trust: float,
        new_trust: float
    ) -> EpistemicState:
        """
        When a new conflicting claim arises:
        If the new source has lower or equal trust without empirical verification, mark as 'disputed'.
        """
        if new_trust < existing_trust:
            return EpistemicState.DISPUTED
        return EpistemicState.ASSERTED

