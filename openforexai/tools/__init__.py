"""Tools package — plug-and-play tool registry for OpenForexAI agents.

All built-in tools are registered in ``DEFAULT_REGISTRY`` at import time.
Add a custom tool with::

    from openforexai.tools import DEFAULT_REGISTRY
    DEFAULT_REGISTRY.register(MyTool())
"""
from openforexai.tools.account.get_account_status import GetAccountStatusTool
from openforexai.tools.account.get_open_positions import GetOpenPositionsTool
from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.dispatcher import ToolDispatcher
from openforexai.tools.market.calculate_indicator import CalculateIndicatorTool

# ── Register built-in tools ───────────────────────────────────────────────────
from openforexai.tools.market.chartshot import ChartShotTool
from openforexai.tools.market.compute_fomak import ComputeFomakTool
from openforexai.tools.market.get_candles import GetCandlesTool
from openforexai.tools.orderbook.get_order import GetOrderTool
from openforexai.tools.orderbook.get_order_book import GetOrderBookTool
from openforexai.tools.orderbook.get_order_trace import GetOrderTraceTool
from openforexai.tools.registry import DEFAULT_REGISTRY, ToolRegistry
from openforexai.tools.sandbox.candle_marker import CandleMarkerTool
from openforexai.tools.sandbox.get_annotation import GetAnnotationTool
from openforexai.tools.sandbox.trade_marker import TradeMarkerTool
from openforexai.tools.sandbox.zone_marker import ZoneMarkerTool
from openforexai.tools.system.alarm import RaiseAlarmTool
from openforexai.tools.system.assessment_memory import AssessmentMemoryTool
from openforexai.tools.system.semantic_memory import SemanticMemoryTool
from openforexai.tools.system.examination_report import CreateExaminationReportTool
from openforexai.tools.system.seed_demo_order import SeedDemoOrderTool
from openforexai.tools.system.get_agent_config import GetAgentConfigTool
from openforexai.tools.system.get_agent_decisions import GetAgentDecisionsTool
from openforexai.tools.system.get_ec_config import GetEcConfigTool
from openforexai.tools.system.get_ec_runs import GetEcRunsTool
from openforexai.tools.system.get_last_decision import GetLastDecisionTool
from openforexai.tools.market.session_status import ForexSessionStatusTool
from openforexai.tools.market.swing_levels import GetSwingLevelsTool
from openforexai.tools.system.manage_sub_prompt import ManageSubPromptTool
from openforexai.tools.news.get_news import GetNewsTool
from openforexai.tools.system.trigger_sync import TriggerSyncTool
from openforexai.tools.trading.auto_place_order import AutoPlaceOrderTool
from openforexai.tools.trading.close_position import ClosePositionTool
from openforexai.tools.trading.modify_order import ModifyOrderTool
from openforexai.tools.trading.place_order import PlaceOrderTool

DEFAULT_REGISTRY.register(GetCandlesTool())
DEFAULT_REGISTRY.register(ComputeFomakTool())
DEFAULT_REGISTRY.register(ChartShotTool())
DEFAULT_REGISTRY.register(CalculateIndicatorTool())
DEFAULT_REGISTRY.register(GetAccountStatusTool())
DEFAULT_REGISTRY.register(GetOpenPositionsTool())
DEFAULT_REGISTRY.register(GetOrderBookTool())
DEFAULT_REGISTRY.register(PlaceOrderTool())
DEFAULT_REGISTRY.register(AutoPlaceOrderTool())
DEFAULT_REGISTRY.register(ModifyOrderTool())
DEFAULT_REGISTRY.register(ClosePositionTool())
DEFAULT_REGISTRY.register(RaiseAlarmTool())
DEFAULT_REGISTRY.register(TriggerSyncTool())
DEFAULT_REGISTRY.register(AssessmentMemoryTool())
DEFAULT_REGISTRY.register(SemanticMemoryTool())
DEFAULT_REGISTRY.register(CreateExaminationReportTool())
DEFAULT_REGISTRY.register(SeedDemoOrderTool())
DEFAULT_REGISTRY.register(GetLastDecisionTool())
DEFAULT_REGISTRY.register(ForexSessionStatusTool())
DEFAULT_REGISTRY.register(GetSwingLevelsTool())
DEFAULT_REGISTRY.register(ManageSubPromptTool())
DEFAULT_REGISTRY.register(GetNewsTool())
DEFAULT_REGISTRY.register(ZoneMarkerTool())
DEFAULT_REGISTRY.register(TradeMarkerTool())
DEFAULT_REGISTRY.register(CandleMarkerTool())
DEFAULT_REGISTRY.register(GetAnnotationTool())
DEFAULT_REGISTRY.register(GetOrderTool())
DEFAULT_REGISTRY.register(GetOrderTraceTool())
DEFAULT_REGISTRY.register(GetAgentConfigTool())
DEFAULT_REGISTRY.register(GetAgentDecisionsTool())
DEFAULT_REGISTRY.register(GetEcConfigTool())
DEFAULT_REGISTRY.register(GetEcRunsTool())

__all__ = [
    "DEFAULT_REGISTRY",
    "ToolRegistry",
    "BaseTool",
    "ToolContext",
    "ToolDispatcher",
]

