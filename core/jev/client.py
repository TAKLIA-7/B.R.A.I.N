import json
import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
import httpx
from core.config import settings

logger = logging.getLogger(__name__)

class JEVRequestError(Exception):
    """Exception raised when an OpenRouter or JEV request fails."""
    pass

@dataclass
class JEVResponse:
    content: Dict[str, Any]
    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    raw_id: str

class OpenRouterJEVClient:
    """
    OpenRouter API gateway adapter for JEV (Judge & Evaluation Validator).
    Submits structured assessment and decision requests to configured LLM models
    via OpenRouter with low temperature, JSON schema mode, and retry resiliency.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_delay: float = 0.5
    ):
        self.api_key = api_key if api_key is not None else settings.OPENROUTER_API_KEY
        self.model = model or settings.OPENROUTER_MODEL
        self.base_url = (base_url or settings.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1").rstrip("/")
        self.timeout = timeout if timeout is not None else settings.JEV_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else settings.JEV_MAX_RETRIES
        self.retry_delay = retry_delay

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://knowledgebrain.ai",
            "X-Title": "Knowledge Brain JEV"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _clean_and_parse_json(self, raw_content: str) -> Dict[str, Any]:
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise JEVRequestError(f"Invalid JSON returned by JEV model: {cleaned[:200]}") from e

    def invoke_json(self, system_prompt: str, user_prompt: str) -> JEVResponse:
        """
        Synchronously invokes OpenRouter with retries and returns parsed JSON.
        """
        if not self.api_key:
            raise JEVRequestError("OPENROUTER_API_KEY is not configured.")

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        attempts = 0
        last_error = None
        start = time.monotonic()

        while attempts < self.max_retries:
            attempts += 1
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, headers=self._headers(), json=payload)

                    if resp.status_code == 401:
                        raise JEVRequestError("OpenRouter 401 Unauthorized. Check OPENROUTER_API_KEY.")
                    if resp.status_code == 429:
                        logger.warning(f"OpenRouter rate limit (429). Attempt {attempts} of {self.max_retries}.")
                        time.sleep(self.retry_delay * attempts)
                        continue
                    if resp.status_code >= 500:
                        logger.warning(f"OpenRouter server error ({resp.status_code}). Attempt {attempts} of {self.max_retries}.")
                        time.sleep(self.retry_delay * attempts)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                    latency_ms = (time.monotonic() - start) * 1000
                    raw_content = ""
                    if data.get("choices") and len(data["choices"]) > 0:
                        raw_content = data["choices"][0].get("message", {}).get("content", "")

                    parsed = self._clean_and_parse_json(raw_content)
                    usage = data.get("usage", {})

                    return JEVResponse(
                        content=parsed,
                        model=self.model,
                        latency_ms=latency_ms,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        raw_id=data.get("id", "")
                    )
            except (httpx.TimeoutException, httpx.RequestError) as e:
                last_error = e
                logger.warning(f"OpenRouter request error: {e}. Attempt {attempts} of {self.max_retries}.")
                time.sleep(self.retry_delay * attempts)
            except JEVRequestError:
                raise

        latency_ms = (time.monotonic() - start) * 1000
        raise JEVRequestError(f"OpenRouter call failed after {self.max_retries} attempts: {last_error}")

    def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.base_url}/auth/key", headers=self._headers())
                return resp.status_code == 200
        except Exception:
            return False

