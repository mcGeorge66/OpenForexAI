from __future__ import annotations

import pytest
from unittest.mock import patch

from openforexai.adapters.llm.azure import AzureOpenAILLMProvider


def test_azure_provider_passes_timeout_seconds_to_client() -> None:
    cfg = {
        "api_key": "test-key",
        "endpoint": "https://example.openai.azure.com",
        "deployment": "gpt-5-mini",
        "api_version": "2024-12-01-preview",
        "retry_attempts": 3,
        "retry_base_delay": 1.0,
        "timeout_seconds": 12.5,
        "sdk_max_retries": 0,
        "transcript_enabled": False,
        "max_tokens": 4096,
    }

    with patch("openforexai.adapters.llm.azure.AsyncAzureOpenAI") as client_cls:
        AzureOpenAILLMProvider.from_config(cfg)

    client_cls.assert_called_once_with(
        api_key="test-key",
        azure_endpoint="https://example.openai.azure.com",
        api_version="2024-12-01-preview",
        timeout=12.5,
        max_retries=0,
    )


def test_azure_provider_requires_timeout_seconds_in_module_config() -> None:
    cfg = {
        "api_key": "test-key",
        "endpoint": "https://example.openai.azure.com",
        "deployment": "gpt-5-mini",
        "api_version": "2024-12-01-preview",
        "retry_attempts": 3,
        "retry_base_delay": 1.0,
        "sdk_max_retries": 0,
        "transcript_enabled": False,
        "max_tokens": 4096,
    }

    with pytest.raises(ValueError, match="timeout_seconds"):
        AzureOpenAILLMProvider.from_config(cfg)
