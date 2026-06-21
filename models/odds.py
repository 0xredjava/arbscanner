"""Core data models for odds, events, and arbitrage opportunities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Platform(str, Enum):
    POLYMARKET = "polymarket"
    STAKE = "stake"
    BCGAME = "bcgame"
    SHUFFLE = "shuffle"
    CLOUDBET = "cloudbet"
    TGCASINO = "tgcasino"
    THUNDERPICK = "thunderpick"
    THE_ODDS_API = "the_odds_api"


class Sport(str, Enum):
    SOCCER = "soccer"
    NBA = "nba"
    TENNIS = "tennis"
    NFL = "nfl"
    NHL = "nhl"
    MLB = "mlb"
    MMA = "mma"
    ESPORTS = "esports"
    OTHER = "other"


@dataclass(frozen=True)
class OrderBookLevel:
    """One executable CLOB ask level; size is measured in contracts."""

    price: float
    size: float


@dataclass
class MarketOutcome:
    """A single bettable outcome within an event."""

    name: str
    decimal_odds: float
    american_odds: int | None = None
    implied_prob: float | None = None
    liquidity_usd: float | None = None
    token_id: str | None = None  # Polymarket CLOB token
    selection_id: str | None = None
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    ask_levels: list[OrderBookLevel] = field(default_factory=list)
    quote_fetched_at: datetime | None = None
    source_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.implied_prob is None and self.decimal_odds > 0:
            self.implied_prob = 1.0 / self.decimal_odds


@dataclass
class ScrapedEvent:
    """Raw event fetched from a platform scraper."""

    platform: Platform
    sport: Sport
    event_id: str
    home_team: str
    away_team: str
    league: str
    start_time: datetime | None
    market_type: str  # e.g. "moneyline", "1x2", "totals", "prediction"
    outcomes: list[MarketOutcome]
    url: str | None = None
    is_live: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
    country: str = ""
    competition: str = ""

    def __post_init__(self) -> None:
        if not self.competition:
            self.competition = self.league
        if not self.country:
            self.country = infer_country(self.league, self.sport)

    @property
    def display_name(self) -> str:
        if self.home_team and self.away_team:
            return f"{self.home_team} vs {self.away_team}"
        return self.home_team or self.away_team or self.event_id


@dataclass
class NormalizedOdds:
    """Platform-agnostic normalized odds record."""

    platform: Platform
    sport: Sport
    event_key: str
    home_team: str
    away_team: str
    league: str
    start_time: datetime | None
    market_type: str
    outcome_name: str
    decimal_odds: float
    american_odds: int
    implied_prob: float
    fee_adjusted_prob: float
    liquidity_usd: float | None
    url: str | None
    event_id: str
    selection_id: str | None = None
    token_id: str | None = None
    country: str = ""
    competition: str = ""
    quote_fetched_at: datetime | None = None
    source_timestamp: datetime | None = None
    ask_levels: list[OrderBookLevel] = field(default_factory=list)


@dataclass
class EventMatch:
    """A group of scraped events believed to represent the same real-world fixture."""

    match_id: str
    sport: Sport
    home_team: str
    away_team: str
    league: str
    start_time: datetime | None
    events: list[ScrapedEvent]
    confidence: float


@dataclass
class StakeAllocation:
    """Recommended stake for one leg of an arbitrage."""

    platform: Platform
    outcome_name: str
    decimal_odds: float
    stake: float
    potential_return: float
    url: str | None
    fee_pct: float
    outcome_key: str = ""
    bet_type: str = "sportsbook"
    price: float | None = None
    average_price: float | None = None
    shares: float | None = None
    gross_payout: float = 0.0
    net_payout: float = 0.0
    fee_amount: float = 0.0
    quote_fetched_at: datetime | None = None
    source_timestamp: datetime | None = None
    best_price_size: float | None = None
    depth_used: list[dict[str, float]] = field(default_factory=list)
    available_depth: list[dict[str, float]] = field(default_factory=list)
    token_id: str | None = None
    selection_id: str | None = None
    minimum_decimal_odds: float | None = None
    maximum_price: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage with stake sizing."""

    match_id: str
    sport: Sport
    event_name: str
    league: str
    market_type: str
    profit_pct: float
    total_stake: float
    guaranteed_return: float
    guaranteed_profit: float
    legs: list[StakeAllocation]
    detected_at: datetime
    min_liquidity_usd: float | None
    warnings: list[str] = field(default_factory=list)
    fingerprint: str = ""
    country: str = ""
    competition: str = ""
    start_time: datetime | None = None
    last_verified_at: datetime | None = None
    quote_expires_at: datetime | None = None
    freshness_status: str = "unknown"
    execution_safe: bool = False
    requested_bankroll: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "sport": self.sport.value,
            "event_name": self.event_name,
            "league": self.league,
            "market_type": self.market_type,
            "profit_pct": round(self.profit_pct, 4),
            "total_stake": round(self.total_stake, 2),
            "guaranteed_return": round(self.guaranteed_return, 2),
            "guaranteed_profit": round(self.guaranteed_profit, 2),
            "detected_at": self.detected_at.isoformat(),
            "min_liquidity_usd": self.min_liquidity_usd,
            "warnings": self.warnings,
            "fingerprint": self.fingerprint,
            "country": self.country,
            "competition": self.competition or self.league,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "last_verified_at": self.last_verified_at.isoformat() if self.last_verified_at else None,
            "quote_expires_at": self.quote_expires_at.isoformat() if self.quote_expires_at else None,
            "freshness_status": self.freshness_status,
            "execution_safe": self.execution_safe,
            "requested_bankroll": round(self.requested_bankroll or self.total_stake, 2),
            "legs": [
                {
                    "platform": leg.platform.value,
                    "outcome": leg.outcome_name,
                    "odds": leg.decimal_odds,
                    "stake": round(leg.stake, 2),
                    "return": round(leg.potential_return, 2),
                    "url": leg.url,
                    "fee_pct": leg.fee_pct,
                    "outcome_key": leg.outcome_key,
                    "bet_type": leg.bet_type,
                    "price": leg.price,
                    "average_price": leg.average_price,
                    "shares": round(leg.shares, 4) if leg.shares is not None else None,
                    "gross_payout": round(leg.gross_payout, 2),
                    "net_payout": round(leg.net_payout, 2),
                    "fee_amount": round(leg.fee_amount, 4),
                    "quote_fetched_at": leg.quote_fetched_at.isoformat() if leg.quote_fetched_at else None,
                    "source_timestamp": leg.source_timestamp.isoformat() if leg.source_timestamp else None,
                    "best_price_size": leg.best_price_size,
                    "depth_used": leg.depth_used,
                    "available_depth": leg.available_depth,
                    "token_id": leg.token_id,
                    "selection_id": leg.selection_id,
                    "minimum_decimal_odds": leg.minimum_decimal_odds,
                    "maximum_price": leg.maximum_price,
                    "warnings": leg.warnings,
                }
                for leg in self.legs
            ],
        }


def infer_country(league: str, sport: Sport) -> str:
    """Conservative display-only geography inference from source competition text."""
    text = (league or "").casefold()
    hints = {
        "brazil": "Brazil", "brasil": "Brazil", "premier league": "England",
        "la liga": "Spain", "bundesliga": "Germany", "ligue 1": "France",
        "serie a": "Italy", "mls": "United States", "argentina": "Argentina",
        "mexico": "Mexico", "colombia": "Colombia", "portugal": "Portugal",
        "netherlands": "Netherlands", "eredivisie": "Netherlands",
    }
    for needle, country in hints.items():
        if needle in text:
            return country
    if sport in {Sport.NBA, Sport.NFL, Sport.NHL, Sport.MLB}:
        return "United States / Canada"
    return "International / unknown"
