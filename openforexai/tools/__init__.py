"""Tools package — plug-and-play tool registry for OpenForexAI agents.

All built-in tools are registered in ``DEFAULT_REGISTRY`` at import time.
Add a custom tool with::

    from openforexai.tools import DEFAULT_REGISTRY
    DEFAULT_REGISTRY.register(MyTool())
"""
from openforexai.tools.registry import DEFAULT_REGISTRY, ToolRegistry
from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.dispatcher import ToolDispatcher

# ── Register built-in tools ───────────────────────────────────────────────────

from openforexai.tools.market.get_candles import GetCandlesTool
from openforexai.tools.market.calculate_indicator import CalculateIndicatorTool
from openforexai.tools.account.get_account_status import GetAccountStatusTool
from openforexai.tools.account.get_open_positions import GetOpenPositionsTool
from openforexai.tools.orderbook.get_order_book import GetOrderBookTool
from openforexai.tools.trading.place_order import PlaceOrderTool
from openforexai.tools.trading.close_position import ClosePositionTool
from openforexai.tools.system.alarm import RaiseAlarmTool
from openforexai.tools.system.trigger_sync import TriggerSyncTool

DEFAULT_REGISTRY.register(GetCandlesTool())
DEFAULT_REGISTRY.register(CalculateIndicatorTool())
DEFAULT_REGISTRY.register(GetAccountStatusTool())
DEFAULT_REGISTRY.register(GetOpenPositionsTool())
DEFAULT_REGISTRY.register(GetOrderBookTool())
DEFAULT_REGISTRY.register(PlaceOrderTool())
DEFAULT_REGISTRY.register(ClosePositionTool())
DEFAULT_REGISTRY.register(RaiseAlarmTool())
DEFAULT_REGISTRY.register(TriggerSyncTool())

__all__ = [
    "DEFAULT_REGISTRY",
    "ToolRegistry",
    "BaseTool",
    "ToolContext",
    "ToolDispatcher",
]

