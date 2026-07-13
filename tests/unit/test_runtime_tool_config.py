from openforexai.config.config_service import ConfigService


def test_runtime_tool_config_matches_analysis_agent_policy() -> None:
    cfg = ConfigService.resolve_runtime_tool_config("OXS_T-EURUSD-AA-ANLYS")

    assert cfg["allowed_tools"] == [
        "get_candles",
        "calculate_indicator",
        "get_order_book",
        "raise_alarm",
        "trigger_sync",
    ]
    assert "pattern" not in cfg
    assert "_comment" not in cfg


def test_runtime_tool_config_matches_broker_agent_policy() -> None:
    cfg = ConfigService.resolve_runtime_tool_config("OXS_T-ALL___-BA-ANLYS")

    assert cfg["allowed_tools"] == [
        "get_account_status",
        "get_open_positions",
        "get_order_book",
        "auto_place_order",
        "modify_order",
        "close_position",
        "raise_alarm",
    ]
