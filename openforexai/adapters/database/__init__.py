from openforexai.adapters.database.sqlite import SQLiteRepository
from openforexai.adapters.database.postgresql import PostgreSQLRepository
from openforexai.registry.plugin_registry import PluginRegistry

PluginRegistry.register_repository("sqlite", SQLiteRepository)
PluginRegistry.register_repository("postgresql", PostgreSQLRepository)

__all__ = ["SQLiteRepository", "PostgreSQLRepository"]
