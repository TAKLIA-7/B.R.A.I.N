import math
import hashlib
from typing import List, Optional
from core.config import settings

class EmbeddingGenerator:
    """Generates normalized vector embeddings for semantic retrieval via pgvector."""

    def __init__(self, provider: Optional[str] = None, dimension: Optional[int] = None):
        self.provider = provider or settings.EMBEDDING_PROVIDER
        self.dimension = dimension or settings.EMBEDDING_DIMENSION

    def generate_embedding(self, text: str) -> List[float]:
        """Generates a normalized float vector of length self.dimension."""
        if not text.strip():
            return [0.0] * self.dimension

        if self.provider == "openai" and settings.OPENAI_API_KEY:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                resp = client.embeddings.create(
                    input=text,
                    model=settings.EMBEDDING_MODEL
                )
                vec = resp.data[0].embedding
                if len(vec) == self.dimension:
                    return vec
            except Exception:
                pass  # Fallback to deterministic normalized embedding

        return self._generate_deterministic_vector(text)

    def _generate_deterministic_vector(self, text: str) -> List[float]:
        """
        Produces a repeatable, pseudo-semantic normalized vector for tests and offline usage.
        Employs character n-grams and word tokens to ensure morphological variants
        (e.g., 'router' and 'routing', 'async' and 'asynchronous') map to similar vector directions.
        """
        vec = [0.0] * self.dimension
        words = text.lower().split()
        tokens = []

        for w in words:
            # Strip punctuation
            clean_w = "".join(ch for ch in w if ch.isalnum())
            if not clean_w:
                continue
            tokens.append(clean_w)
            # Add character 3-grams and 4-grams for subword similarity
            for n in (3, 4):
                if len(clean_w) >= n:
                    for i in range(len(clean_w) - n + 1):
                        tokens.append(clean_w[i:i+n])

        for idx, tok in enumerate(tokens):
            h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
            pos = h % self.dimension
            sign = 1.0 if ((h >> 4) % 2 == 0) else -1.0
            weight = 1.0 / math.log(idx + 2.0)
            vec[pos] += sign * weight

        # Normalize to unit length
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            return [round(x / norm, 6) for x in vec]

        vec[0] = 1.0
        return vec
