"""Normalize odds across platforms to a common format."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from models.odds import NormalizedOdds, Platform, ScrapedEvent


class OddsNormalizer:
    PLATFORM_FEES: dict[Platform, float] = {
        Platform.POLYMARKET: 0.0,
        Platform.STAKE: 0.0,
        Platform.BCGAME: 0.0,
        Platform.SHUFFLE: 0.0,
        Platform.CLOUDBET: 0.0,
        Platform.TGCASINO: 0.0,
        Platform.THUNDERPICK: 0.0,
        Platform.THE_ODDS_API: 0.0,
    }

    def __init__(self, default_fee_pct: float = 2.0, slippage_pct: float = 1.0) -> None:
        self.default_fee_pct = default_fee_pct
        self.slippage_pct = slippage_pct

    def normalize_event(self, event: ScrapedEvent) -> list[NormalizedOdds]:
        fee_pct = self.PLATFORM_FEES.get(event.platform, self.default_fee_pct)
        records: list[NormalizedOdds] = []

        for outcome in event.outcomes:
            decimal = outcome.decimal_odds
            if decimal <= 1.0:
                continue

            american = self.decimal_to_american(decimal)
            implied = 1.0 / decimal
            if event.platform == Platform.POLYMARKET:
                try:
                    fee_rate = float(outcome.raw.get("fee_rate", 0.0))
                except (TypeError, ValueError):
                    fee_rate = 0.0
                fee_adjusted = implied + fee_rate * implied * (1 - implied)
            else:
                fee_adjusted = implied / max(1 - fee_pct / 100, 0.000001)
            fee_adjusted /= max(1 - self.slippage_pct / 100, 0.000001)

            records.append(
                NormalizedOdds(
                    platform=event.platform,
                    sport=event.sport,
                    event_key=self.build_event_key(event),
                    home_team=self.clean_team_name(event.home_team),
                    away_team=self.clean_team_name(event.away_team),
                    league=event.league,
                    start_time=event.start_time,
                    market_type=event.market_type,
                    outcome_name=self.clean_outcome_name(outcome.name),
                    decimal_odds=decimal,
                    american_odds=american,
                    implied_prob=implied,
                    fee_adjusted_prob=fee_adjusted,
                    liquidity_usd=outcome.liquidity_usd,
                    url=outcome.url or event.url,
                    event_id=event.event_id,
                    selection_id=outcome.selection_id,
                    token_id=outcome.token_id,
                    country=event.country,
                    competition=event.competition,
                    quote_fetched_at=outcome.quote_fetched_at,
                    source_timestamp=outcome.source_timestamp,
                    ask_levels=list(outcome.ask_levels),
                )
            )
        return records

    def normalize_all(self, events: list[ScrapedEvent]) -> list[NormalizedOdds]:
        results: list[NormalizedOdds] = []
        for event in events:
            results.extend(self.normalize_event(event))
        return results

    @staticmethod
    def decimal_to_american(decimal: float) -> int:
        if decimal >= 2.0:
            return int(round((decimal - 1) * 100))
        return int(round(-100 / (decimal - 1)))

    @staticmethod
    def american_to_decimal(american: int) -> float:
        if american > 0:
            return 1 + american / 100
        return 1 + 100 / abs(american)

    @staticmethod
    def clean_team_name(name: str) -> str:
        name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        name = re.sub(r"[^\w\s]", "", name.lower())
        name = re.sub(
            r"\b(fc|cf|sc|afc|club|the)\b",
            "",
            name,
        )
        return re.sub(r"\s+", " ", name).strip()

    @staticmethod
    def clean_outcome_name(name: str) -> str:
        return re.sub(r"\s+", " ", name.strip().lower())

    def build_event_key(self, event: ScrapedEvent) -> str:
        home = self.clean_team_name(event.home_team)
        away = self.clean_team_name(event.away_team)
        teams = "|".join(sorted([home, away]))
        date_part = ""
        if event.start_time:
            date_part = event.start_time.strftime("%Y%m%d")
        return f"{event.sport.value}:{teams}:{date_part}:{event.market_type}"
