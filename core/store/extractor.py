import json
import logging
import re
from typing import List, Optional
from core.models.memory import ExtractedMemoryCandidate, MemoryType
from core.models.ingest import IngestRequest
from core.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """
You are Knowledge Brain's Memory Extraction Engine.
Extract meaningful persistent memory candidates from the provided content into a valid JSON array of objects.
Do not extract transient conversation filler.
Supported memory types: "fact", "preference", "decision", "task", "experience", "procedure".

Each JSON object must have:
- type: string (one of the 6 types above)
- subject: string or null
- predicate: string or null
- object: string or null
- text: string (clear, normalized statement)
- importance: float between 0.0 and 1.0
- confidence: float between 0.0 and 1.0
- message_ref: string or null
- requires_semantic_search: boolean (default true)
- has_meaningful_relationships: boolean (default false)
- resumable: boolean (default false)

Output ONLY raw JSON array.
"""

class MemoryExtractor:
    """Extracts structured memory candidates from ingested conversation/document content."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or settings.EXTRACTION_LLM_PROVIDER

    def extract_candidates(self, request: IngestRequest) -> List[ExtractedMemoryCandidate]:
        raw_text = self._combine_text(request)
        if not raw_text.strip():
            return []

        if self.provider == "gemini" and settings.GEMINI_API_KEY:
            try:
                return self._extract_via_gemini(raw_text)
            except Exception as e:
                logger.warning(f"Gemini extraction failed: {e}. Falling back to deterministic extractor.")
                return self._extract_deterministic(raw_text)
        else:
            return self._extract_deterministic(raw_text)

    def _combine_text(self, request: IngestRequest) -> str:
        parts = []
        if request.content:
            parts.append(request.content)
        if request.messages:
            for m in request.messages:
                parts.append(f"{m.role}: {m.content}")
        if request.document:
            title = f"Document '{request.document.title}': " if request.document.title else "Document: "
            parts.append(f"{title}{request.document.content}")
        if request.tool_output:
            parts.append(f"Tool '{request.tool_output.tool_name}' output: {request.tool_output.output}")
        return "\n".join(parts)

    def _extract_via_gemini(self, text: str) -> List[ExtractedMemoryCandidate]:
        # Using Google Generative AI / google-genai
        from google import genai
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=f"{EXTRACTION_SYSTEM_PROMPT}\n\nContent to extract:\n{text}",
            config={"response_mime_type": "application/json"}
        )
        json_data = json.loads(response.text)
        candidates = []
        for item in json_data:
            candidate = ExtractedMemoryCandidate(**item)
            candidates.append(candidate)
        return candidates

    def _extract_deterministic(self, text: str) -> List[ExtractedMemoryCandidate]:
        """
        Deterministic, robust rule-based extractor for tests and offline/local development.
        Extracts structured statements matching facts, decisions, tasks, and preferences.
        """
        candidates: List[ExtractedMemoryCandidate] = []
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        for line in lines:
            # Check for decisions
            if any(k in line.lower() for k in ["decided", "decision", "chose", "selected", "will use"]):
                candidates.append(ExtractedMemoryCandidate(
                    type=MemoryType.DECISION,
                    text=line,
                    importance=0.85,
                    confidence=0.9
                ))
            # Check for tasks
            elif any(k in line.lower() for k in ["task", "todo", "need to", "must implement", "plan to"]):
                candidates.append(ExtractedMemoryCandidate(
                    type=MemoryType.TASK,
                    text=line,
                    importance=0.8,
                    confidence=0.85,
                    resumable=True
                ))
            # Check for preferences
            elif any(k in line.lower() for k in ["prefer", "preference", "favor"]):
                candidates.append(ExtractedMemoryCandidate(
                    type=MemoryType.PREFERENCE,
                    text=line,
                    importance=0.7,
                    confidence=0.8
                ))
            # Check for planted claims or facts
            elif any(k in line.lower() for k in ["claim", "port", "database", "is", "uses", "runs on"]):
                candidates.append(ExtractedMemoryCandidate(
                    type=MemoryType.FACT,
                    text=line,
                    importance=0.6,
                    confidence=0.8
                ))

        if not candidates and text.strip():
            # General fallback fact
            candidates.append(ExtractedMemoryCandidate(
                type=MemoryType.FACT,
                text=text.strip()[:500],
                importance=0.5,
                confidence=0.7
            ))

        return candidates

