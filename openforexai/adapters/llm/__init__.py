from openforexai.adapters.llm.anthropic import AnthropicLLMProvider
from openforexai.adapters.llm.openai import OpenAILLMProvider, LMStudioLLMProvider
from openforexai.adapters.llm.azure import AzureOpenAILLMProvider
from openforexai.registry.plugin_registry import PluginRegistry

PluginRegistry.register_llm_provider("anthropic", AnthropicLLMProvider)
PluginRegistry.register_llm_provider("openai", OpenAILLMProvider)
PluginRegistry.register_llm_provider("lmstudio", LMStudioLLMProvider)
PluginRegistry.register_llm_provider("azure", AzureOpenAILLMProvider)

__all__ = ["AnthropicLLMProvider", "OpenAILLMProvider", "LMStudioLLMProvider", "AzureOpenAILLMProvider"]

