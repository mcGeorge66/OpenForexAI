from openforexai.adapters.llm.anthropic import AnthropicLLMProvider
from openforexai.adapters.llm.azure import AzureOpenAILLMProvider
from openforexai.adapters.llm.lmstudio import LMStudioLLMProvider
from openforexai.adapters.llm.ollama import OllamaLLMProvider
from openforexai.adapters.llm.openai import OpenAILLMProvider
from openforexai.registry.plugin_registry import PluginRegistry

PluginRegistry.register_llm_provider("anthropic", AnthropicLLMProvider)
PluginRegistry.register_llm_provider("openai", OpenAILLMProvider)
PluginRegistry.register_llm_provider("lmstudio", LMStudioLLMProvider)
PluginRegistry.register_llm_provider("ollama", OllamaLLMProvider)
PluginRegistry.register_llm_provider("azure", AzureOpenAILLMProvider)

__all__ = [
    "AnthropicLLMProvider",
    "OpenAILLMProvider",
    "LMStudioLLMProvider",
    "OllamaLLMProvider",
    "AzureOpenAILLMProvider",
]
