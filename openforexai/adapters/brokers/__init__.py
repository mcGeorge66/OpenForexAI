from openforexai.adapters.brokers.oanda import OANDABroker
from openforexai.adapters.brokers.mt5 import MT5Broker
from openforexai.registry.plugin_registry import PluginRegistry

PluginRegistry.register_broker("oanda", OANDABroker)
PluginRegistry.register_broker("mt5", MT5Broker)

__all__ = ["OANDABroker", "MT5Broker"]
