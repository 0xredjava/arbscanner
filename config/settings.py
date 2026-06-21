"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    log_level: str = "INFO"
    refresh_interval_seconds: int = Field(default=60, validation_alias="SCAN_INTERVAL_SECONDS")
    min_profit_pct: float = 2.0
    default_bankroll: float = 1000.0
    admin_token: str = ""
    cors_origins: str = "http://localhost:3000"

    # Fee / slippage assumptions (percent)
    default_platform_fee_pct: float = 2.0
    slippage_pct: float = 1.0
    liquidity_buffer_pct: float = 5.0

    # Watched sports (comma-separated in .env)
    watched_sports: str = "soccer,nba,tennis,nfl,nhl,mlb"

    # Polymarket
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_url: str = "https://clob.polymarket.com"
    polymarket_data_url: str = "https://data-api.polymarket.com"

    # The Odds API (optional fallback aggregator)
    the_odds_api_key: str = ""
    the_odds_api_url: str = "https://api.the-odds-api.com/v4"

    # Cloudbet (public, no key required for odds)
    cloudbet_api_url: str = "https://sports-api.cloudbet.com/pub/v2"

    # Supabase persistence
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Server-side browser fallback. Proxies and logged-in sessions are intentionally unsupported.
    use_playwright_headless: bool = True
    playwright_timeout_ms: int = 30000

    # Platform toggles
    enable_polymarket: bool = True
    enable_stake: bool = True
    enable_bcgame: bool = True
    enable_shuffle: bool = True
    enable_cloudbet: bool = True
    enable_tgcasino: bool = True
    enable_thunderpick: bool = True

    # Output
    json_log_path: Path = Field(default=PROJECT_ROOT / "data" / "arbs.json")

    # Matcher
    fuzzy_match_threshold: int = 75
    max_event_time_diff_minutes: int = 120

    @field_validator("json_log_path", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        p = Path(v)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @model_validator(mode="after")
    def enforce_public_data_mode(self) -> Settings:
        """Keep v1 limited to public/no-login market data."""
        return self

    @property
    def sports_list(self) -> list[str]:
        return [s.strip().lower() for s in self.watched_sports.split(",") if s.strip()]

    @property
    def proxies(self) -> list[str]:
        return []

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def enabled_platforms(self) -> list[str]:
        platforms: list[str] = []
        if self.enable_polymarket:
            platforms.append("polymarket")
        if self.enable_stake:
            platforms.append("stake")
        if self.enable_bcgame:
            platforms.append("bcgame")
        if self.enable_shuffle:
            platforms.append("shuffle")
        if self.enable_cloudbet:
            platforms.append("cloudbet")
        if self.enable_tgcasino:
            platforms.append("tgcasino")
        if self.enable_thunderpick:
            platforms.append("thunderpick")
        return platforms


@lru_cache
def get_settings() -> Settings:
    return Settings()
