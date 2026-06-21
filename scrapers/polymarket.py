"""Polymarket integration via Gamma API + CLOB API.

Public endpoints (no auth required for market data):
- Gamma: https://gamma-api.polymarket.com
- CLOB:  https://clob.polymarket.com

This scanner uses public market-data endpoints only. It does not place orders.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from config.settings import Settings
from models.odds import MarketOutcome, Platform, ScrapedEvent, Sport
from scrapers.base import BaseScraper
from utils.http import AsyncHttpClient
from utils.proxy import ProxyRotator

logger = logging.getLogger("arb_scanner.scrapers.polymarket")

# Sport tag mapping (discovered via GET /sports on Gamma API)
SPORT_TAG_MAP: dict[str, Sport] = {
    "soccer": Sport.SOCCER,
    "nba": Sport.NBA,
    "nfl": Sport.NFL,
    "nhl": Sport.NHL,
    "mlb": Sport.MLB,
    "tennis": Sport.TENNIS,
    "mma": Sport.MMA,
    "esports": Sport.ESPORTS,
}

SPORT_KEYWORDS: dict[Sport, list[str]] = {
    Sport.SOCCER: ["soccer", "premier league", "la liga", "bundesliga", "serie a", "mls", "champions league"],
    Sport.NBA: ["nba", "basketball"],
    Sport.TENNIS: ["tennis", "atp", "wta"],
    Sport.NFL: ["nfl", "super bowl"],
    Sport.NHL: ["nhl", "hockey"],
    Sport.MLB: ["mlb", "baseball"],
}


class PolymarketScraper(BaseScraper):
    platform = Platform.POLYMARKET
    fee_pct = 0.0  # Polymarket has no traditional vig; spread is in the book

    def __init__(
        self,
        settings: Settings,
        http: AsyncHttpClient,
        proxy_rotator: ProxyRotator,
    ) -> None:
        super().__init__(settings, http, proxy_rotator)
        self.gamma_url = settings.polymarket_gamma_url.rstrip("/")
        self.clob_url = settings.polymarket_clob_url.rstrip("/")

    async def fetch_events(self) -> list[ScrapedEvent]:
        events: list[ScrapedEvent] = []
        watched = set(self.settings.sports_list)

        # Strategy 1: Sports-tagged events via Gamma
        sports_meta = await self._fetch_sports_metadata()
        for sport_entry in sports_meta:
            tag_id = sport_entry.get("id") or sport_entry.get("tag_id")
            sport_key = (sport_entry.get("sport") or sport_entry.get("slug") or "").lower()
            if sport_key not in watched and not any(k in sport_key for k in watched):
                continue
            sport = SPORT_TAG_MAP.get(sport_key, self._infer_sport(sport_entry))
            if tag_id:
                gamma_events = await self._fetch_events_by_tag(tag_id)
                for ge in gamma_events:
                    parsed = self._parse_gamma_event(ge, sport)
                    events.extend(parsed)

        # Strategy 2: High-volume active events (catches non-sports-tagged markets)
        if len(events) < 10:
            all_active = await self._fetch_active_events(limit=100)
            for ge in all_active:
                sport = self._infer_sport_from_text(ge.get("title", "") + " " + ge.get("description", ""))
                if sport.value not in watched and Sport.OTHER.value not in watched:
                    continue
                parsed = self._parse_gamma_event(ge, sport)
                events.extend(parsed)

        # Enrich with CLOB orderbook prices where available
        await self._enrich_with_clob_prices(events)
        return events

    async def _fetch_sports_metadata(self) -> list[dict[str, Any]]:
        try:
            data = await self.http.get(f"{self.gamma_url}/sports")
            return data if isinstance(data, list) else []
        except Exception:
            logger.warning("Could not fetch Polymarket sports metadata")
            return []

    async def _fetch_events_by_tag(self, tag_id: int | str) -> list[dict[str, Any]]:
        params = {
            "tag_id": tag_id,
            "active": "true",
            "closed": "false",
            "limit": 50,
            "order": "volume_24hr",
            "ascending": "false",
        }
        data = await self.http.get(f"{self.gamma_url}/events", params=params)
        return data if isinstance(data, list) else []

    async def _fetch_active_events(self, limit: int = 100) -> list[dict[str, Any]]:
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume_24hr",
            "ascending": "false",
        }
        data = await self.http.get(f"{self.gamma_url}/events", params=params)
        return data if isinstance(data, list) else []

    def _parse_gamma_event(self, event: dict[str, Any], sport: Sport) -> list[ScrapedEvent]:
        results: list[ScrapedEvent] = []
        markets = event.get("markets") or []
        title = event.get("title") or ""
        slug = event.get("slug") or event.get("id", "")
        start_time = self._parse_datetime(event.get("startDate") or event.get("start_date"))
        url = f"https://polymarket.com/event/{slug}"

        for market in markets:
            if market.get("closed") or not market.get("active", True):
                continue
            outcomes, prices = self._parse_outcomes_prices(market)
            if not outcomes:
                continue

            token_ids = self._parse_token_ids(market)
            home, away = self._extract_teams(title, outcomes)

            market_outcomes: list[MarketOutcome] = []
            for i, (outcome_name, price) in enumerate(zip(outcomes, prices)):
                if price <= 0 or price >= 1:
                    continue
                decimal_odds = 1.0 / price
                token_id = token_ids[i] if i < len(token_ids) else None
                market_outcomes.append(
                    MarketOutcome(
                        name=outcome_name,
                        decimal_odds=decimal_odds,
                        implied_prob=price,
                        liquidity_usd=self._safe_float(market.get("liquidity")),
                        token_id=token_id,
                        selection_id=str(market.get("id", "")),
                        url=url,
                        raw={"gamma_price": price, "market": market},
                    )
                )

            if not market_outcomes:
                continue

            results.append(
                ScrapedEvent(
                    platform=Platform.POLYMARKET,
                    sport=sport,
                    event_id=str(market.get("id") or event.get("id")),
                    home_team=home,
                    away_team=away,
                    league=event.get("seriesSlug") or sport.value,
                    start_time=start_time,
                    market_type=self._detect_market_type(title, outcomes),
                    outcomes=market_outcomes,
                    url=url,
                    is_live=event.get("live", False),
                    raw={"event": event, "market": market},
                )
            )
        return results

    async def _enrich_with_clob_prices(self, events: list[ScrapedEvent]) -> None:
        """Fetch best ask prices from CLOB for more accurate executable odds."""
        token_ids = []
        token_map: dict[str, tuple[ScrapedEvent, MarketOutcome]] = {}
        for event in events:
            for outcome in event.outcomes:
                if outcome.token_id:
                    token_ids.append(outcome.token_id)
                    token_map[outcome.token_id] = (event, outcome)

        if not token_ids:
            return

        # Batch price requests (CLOB supports POST /prices)
        batch_size = 50
        for i in range(0, len(token_ids), batch_size):
            batch = token_ids[i : i + batch_size]
            try:
                body = [{"token_id": tid, "side": "BUY"} for tid in batch]
                prices_data = await self.http.post(f"{self.clob_url}/prices", json=body)
                if isinstance(prices_data, dict):
                    for tid, price_str in prices_data.items():
                        if tid in token_map:
                            _, outcome = token_map[tid]
                            price = self._safe_float(price_str)
                            if 0 < price < 1:
                                outcome.decimal_odds = 1.0 / price
                                outcome.implied_prob = price
                                outcome.raw["clob_price"] = price
            except Exception:
                logger.debug("CLOB price enrichment failed for batch %d", i)

    @staticmethod
    def _parse_outcomes_prices(market: dict[str, Any]) -> tuple[list[str], list[float]]:
        outcomes_raw = market.get("outcomes", "[]")
        prices_raw = market.get("outcomePrices", "[]")
        if isinstance(outcomes_raw, str):
            outcomes = json.loads(outcomes_raw)
        else:
            outcomes = outcomes_raw or []
        if isinstance(prices_raw, str):
            prices = [float(p) for p in json.loads(prices_raw)]
        else:
            prices = [float(p) for p in (prices_raw or [])]
        return list(outcomes), prices

    @staticmethod
    def _parse_token_ids(market: dict[str, Any]) -> list[str]:
        clob_ids = market.get("clobTokenIds", "[]")
        if isinstance(clob_ids, str):
            return json.loads(clob_ids)
        return list(clob_ids or [])

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _extract_teams(title: str, outcomes: list[str]) -> tuple[str, str]:
        """Best-effort team extraction from event title."""
        separators = [" vs. ", " vs ", " v ", " @ ", " at "]
        lower = title.lower()
        for sep in separators:
            if sep in lower:
                idx = lower.index(sep)
                return title[:idx].strip(), title[idx + len(sep) :].strip()
        if len(outcomes) == 2:
            return outcomes[0], outcomes[1]
        return title, ""

    @staticmethod
    def _detect_market_type(title: str, outcomes: list[str]) -> str:
        title_lower = title.lower()
        if "o/u" in title_lower or "over" in title_lower or "under" in title_lower:
            return "totals"
        if len(outcomes) == 2:
            return "moneyline"
        if len(outcomes) == 3:
            return "1x2"
        return "prediction"

    def _infer_sport(self, entry: dict[str, Any]) -> Sport:
        text = json.dumps(entry).lower()
        return self._infer_sport_from_text(text)

    def _infer_sport_from_text(self, text: str) -> Sport:
        text = text.lower()
        for sport, keywords in SPORT_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return sport
        return Sport.OTHER
