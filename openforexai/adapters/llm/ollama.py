from __future__ import annotations

from openforexai.adapters.llm.openai import OpenAILLMProvider


class OllamaLLMProvider(OpenAILLMProvider):
    """Ollama adapter (OpenAI-compatible local endpoint)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434/v1",
        model: str = "llama3.1",
        api_key: str = "ollama",
        retry_attempts: int = 3,
        retry_base_delay: float = 1.0,
        default_temperature: float | None = 0.1,
        default_max_tokens: int = 4096,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            retry_attempts=retry_attempts,
            retry_base_delay=retry_base_delay,
            default_temperature=default_temperature,
            default_max_tokens=default_max_tokens,
        )

    @classmethod
    def from_config(cls, cfg: dict) -> OllamaLLMProvider:
        return cls(
            base_url=cfg.get("base_url", "http://127.0.0.1:11434/v1"),
            model=cfg.get("model", "llama3.1"),
            api_key=cfg.get("api_key", "ollama"),
            retry_attempts=cfg.get("retry_attempts", 3),
            retry_base_delay=cfg.get("retry_base_delay", 1.0),
            default_temperature=(
                cfg.get("temperature") if isinstance(cfg.get("temperature"), (int, float)) else 0.1
            ),
            default_max_tokens=cfg.get("max_tokens", 4096),
        )
