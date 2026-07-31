from __future__ import annotations

from unittest.mock import patch

from openforexai.adapters.llm.openai import OpenAILLMProvider


def test_openai_provider_passes_base_url_and_timeout_to_client() -> None:
    """Covers the Azure-via-base_url path too — Azure AI Foundry's v1 API is
    fully OpenAI-compatible (no api-version, no separate AzureOpenAI client),
    so it's configured as adapter "openai" with base_url pointed at the
    resource's /openai/v1 endpoint."""
    cfg = {
        "api_key": "test-key",
        "base_url": "https://example.services.ai.azure.com/openai/v1",
        "model": "gpt-5-mini",
        "retry_attempts": 3,
        "retry_base_delay": 1.0,
        "timeout_seconds": 12.5,
        "sdk_max_retries": 0,
        "transcript_enabled": False,
        "max_tokens": 4096,
    }

    with patch("openforexai.adapters.llm.openai._openai.AsyncOpenAI") as client_cls:
        OpenAILLMProvider.from_config(cfg)

    client_cls.assert_called_once_with(
        api_key="test-key",
        base_url="https://example.services.ai.azure.com/openai/v1",
        timeout=12.5,
        max_retries=0,
    )


def test_openai_provider_defaults_timeout_when_not_configured() -> None:
    """Unlike the old Azure adapter, timeout_seconds is optional — a 30s
    default keeps every provider on this adapter (OpenAI, LM Studio, Ollama)
    from inheriting the SDK's ~10 minute default (see audit finding on hung
    connections outliving the caller's own timeout)."""
    cfg = {"api_key": "test-key", "model": "gpt-4o"}

    with patch("openforexai.adapters.llm.openai._openai.AsyncOpenAI") as client_cls:
        OpenAILLMProvider.from_config(cfg)

    _, kwargs = client_cls.call_args
    assert kwargs["timeout"] == 30.0
    assert kwargs["max_retries"] == 0


def test_openai_provider_validates_reasoning_effort() -> None:
    import pytest

    with pytest.raises(ValueError, match="reasoning_effort"):
        OpenAILLMProvider.from_config({"api_key": "k", "reasoning_effort": "extreme"})
