import json
import pytest
from unittest.mock import patch, MagicMock
from core.jev.client import OpenRouterJEVClient, JEVRequestError
from core.jev.fallback import DeterministicJEVFallback

def test_headers_and_config():
    client = OpenRouterJEVClient(
        api_key="test-api-key",
        model="google/gemini-2.5-flash",
        base_url="https://openrouter.ai/api/v1",
        timeout=15.0
    )
    headers = client._headers()
    assert headers["Authorization"] == "Bearer test-api-key"
    assert headers["HTTP-Referer"] == "https://knowledgebrain.ai"
    assert headers["X-Title"] == "Knowledge Brain JEV"
    assert client.model == "google/gemini-2.5-flash"

def test_parse_structured_json_response_with_markdown_fences():
    client = OpenRouterJEVClient(api_key="mock-key")
    raw_markdown = "```json\n{\"decision\": \"allow\", \"score\": 0.95}\n```"
    parsed = client._clean_and_parse_json(raw_markdown)
    assert parsed["decision"] == "allow"
    assert parsed["score"] == 0.95

def test_clean_and_parse_invalid_json():
    client = OpenRouterJEVClient(api_key="mock-key")
    with pytest.raises(JEVRequestError) as exc_info:
        client._clean_and_parse_json("not valid json content")
    assert "Invalid JSON returned by JEV model" in str(exc_info.value)

@patch("httpx.Client.post")
def test_openrouter_rate_limit_and_retry(mock_post):
    # Simulate 429 rate limit then success
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.text = "Rate limit exceeded"

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {
        "id": "gen-123",
        "choices": [{"message": {"content": "{\"status\": \"ok\"}"}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20}
    }

    mock_post.side_effect = [mock_resp_429, mock_resp_200]

    client = OpenRouterJEVClient(api_key="test-key", max_retries=2, retry_delay=0.01)
    res = client.invoke_json(
        system_prompt="system",
        user_prompt="user"
    )
    assert res.content["status"] == "ok"
    assert res.prompt_tokens == 50
    assert res.completion_tokens == 20
    assert mock_post.call_count == 2

@patch("httpx.Client.post")
def test_openrouter_unauthorized_error(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_post.return_value = mock_resp

    client = OpenRouterJEVClient(api_key="invalid-key", max_retries=1)
    with pytest.raises(JEVRequestError) as exc:
        client.invoke_json("system", "user")
    assert "401 Unauthorized" in str(exc.value)

def test_deterministic_fallback_ingestion():
    fallback = DeterministicJEVFallback()
    items = fallback.evaluate_ingestion("We decided to use Redis for session caching.")
    assert len(items) >= 1
    decision = items[0].decision
    assert decision.memory_type == "decision"
    assert decision.lifetime == "persistent"
    assert "postgres" in decision.storage_targets

def test_deterministic_fallback_retrieval():
    fallback = DeterministicJEVFallback()
    decision = fallback.evaluate_retrieval(
        query="What is our database strategy?",
        token_budget=500
    )
    assert decision.retrieval_strategy in ("semantic", "hybrid")
    assert decision.include_semantic_search is True
    assert decision.token_budget == 500

