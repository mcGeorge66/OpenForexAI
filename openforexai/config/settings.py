from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-opus-4-6"
    api_key: str = ""
    base_url: str = "http://localhost:1234"  # LM Studio
    temperature: float = 0.1
    max_tokens: int = 1024
    timeout_seconds: int = 30
    retry_attempts: int = 3


class OandaSettings(BaseModel):
    api_key: str = ""
    account_id: str = ""
    practice: bool = True


class MT5Settings(BaseModel):
    login: int = 0
    password: str = ""
    server: str = ""


class BrokerSettings(BaseModel):
    name: str = "oanda"
    practice: bool = True
    oanda: OandaSettings = Field(default_factory=OandaSettings)
    mt5: MT5Settings = Field(default_factory=MT5Settings)


class DatabaseSettings(BaseModel):
    backend: str = "sqlite"
    sqlite_path: str = "./data/openforexai.db"
    database_url: str | None = None
    pool_size: int = 5


class RiskSettings(BaseModel):
    max_risk_per_trade_pct: float = 1.0
    max_total_exposure_pct: float = 5.0
    max_drawdown_pct: float = 10.0
    max_daily_loss_pct: float = 3.0
    max_correlation_threshold: float = 0.7
    max_open_positions: int = 6


class TradingAgentSettings(BaseModel):
    cycle_interval_seconds: int = 60
    analysis_timeout_seconds: float = 15.0


class TechnicalAnalysisSettings(BaseModel):
    max_concurrent_requests: int = 3


class OptimizationSettings(BaseModel):
    min_trades_before_run: int = 20
    backtest_weeks: int = 4
    max_prompt_candidates: int = 3


class AgentsSettings(BaseModel):
    trading: TradingAgentSettings = Field(default_factory=TradingAgentSettings)
    technical_analysis: TechnicalAnalysisSettings = Field(
        default_factory=TechnicalAnalysisSettings
    )
    optimization: OptimizationSettings = Field(default_factory=OptimizationSettings)


class DataSettings(BaseModel):
    rolling_weeks: int = 4
    timeframes: list[str] = Field(default_factory=lambda: ["M1", "M5", "H1", "H4", "D1"])
    indicator_cache_ttl_seconds: int = 30


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPENFOREXAI_",
        env_nested_delimiter="__",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    log_level: str = "INFO"
    cycle_interval_seconds: int = 60
    optimization_interval_hours: int = 6

    pairs: list[str] = Field(default_factory=lambda: ["EURUSD", "USDJPY", "GBPUSD"])
    data: DataSettings = Field(default_factory=DataSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    agents: AgentsSettings = Field(default_factory=AgentsSettings)

    def validate_pairs(self) -> None:
        if not self.pairs:
            raise ValueError("At least one trading pair must be configured in 'pairs'.")
