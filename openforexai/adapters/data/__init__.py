"""Data adapter package — self-registers concrete DataContainer implementations.

Imported by bootstrap.py to trigger PluginRegistry registration.
"""
from openforexai.adapters.data.sqlite import SQLiteDataContainer
from openforexai.adapters.data.postgresql import PostgreSQLDataContainer
from openforexai.registry.plugin_registry import PluginRegistry

PluginRegistry.register_data_container("sqlite",      SQLiteDataContainer)
PluginRegistry.register_data_container("postgresql",  PostgreSQLDataContainer)

# Backward compat: also register under the old repository names so any
# code using PluginRegistry.get_repository() still works.
PluginRegistry.register_repository("sqlite",      SQLiteDataContainer)
PluginRegistry.register_repository("postgresql",  PostgreSQLDataContainer)

__all__ = ["SQLiteDataContainer", "PostgreSQLDataContainer"]
