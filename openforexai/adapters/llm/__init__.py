from openforexai.adapters.llm.anthropic import AnthropicLLMProvider
from openforexai.adapters.llm.openai import OpenAILLMProvider, LMStudioLLMProvider
from openforexai.registry.plugin_registry import PluginRegistry

PluginRegistry.register_llm_provider("anthropic", AnthropicLLMProvider)
PluginRegistry.register_llm_provider("openai", OpenAILLMProvider)
PluginRegistry.register_llm_provider("lmstudio", LMStudioLLMProvider)

__all__ = ["AnthropicLLMProvider", "OpenAILLMProvider", "LMStudioLLMProvider"]
