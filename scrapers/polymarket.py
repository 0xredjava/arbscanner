"""Polymarket integration via Gamma API + CLOB API.

Public endpoints (no auth required for market data):
- Gamma: https://gamma-api.polymarket.com
- CLOB:  https://clob.polymarket.com

This scanner uses public market-data endpoints only. It does not place orders.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
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

SPORT_TAGS: dict[str, tuple[int, Sport]] = {
    "soccer": (100350, Sport.SOCCER),
    "nba": (745, Sport.NBA),
    "nfl": (450, Sport.NFL),
    "nhl": (899, Sport.NHL),
    "mlb": (100381, Sport.MLB),
    "tennis": (864, Sport.TENNIS),
}

SPORT_KEYWORDS: dict[Sport, list[str]] = {
    Sport.SOCCER: ["soccer", "premier league", "la liga", "bundesliga", "serie a", "mls", "champions league"],
    Sport.NBA: ["nba", "basketball"],
    Sport.TENNIS: ["tennis", "atp", "wta"],
    Sport.NFL: ["nfl", "super bowl"],
    Sport.NHL: ["nhl", "hockey"],
    Sport.MLB: ["mlb", "baseball"],
}

MAX_KEYSET_PAGES = 20


class PolymarketScraper(BaseScraper):
    platform = Platform.POLYMARKET
    fee_pct = 0.0  # Polymarket has no traditional vig; spread is in the book
    source_type = "api"

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
        for watched in self.settings.sports_list:
            config = SPORT_TAGS.get(watched)
            if not config:
                continue
            for raw in await self._fetch_events_keyset(config[0]):
                parsed = self._parse_gamma_event(raw, config[1])
                if parsed:
                    events.append(parsed)
        events = list({event.event_id: event for event in events}.values())
        await self._enrich_with_clob_prices(events)
        return events

    async def _fetch_events_keyset(self, tag_id: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        for page in range(MAX_KEYSET_PAGES):
            now = datetime.now(timezone.utc)
            params: dict[str, Any] = {
                "tag_id": tag_id,
                "closed": "false",
                "limit": 500,
                "start_time_min": now.isoformat(),
                "start_time_max": (now + timedelta(days=self.settings.max_event_horizon_days)).isoformat(),
            }
            if cursor:
                params["after_cursor"] = cursor
            data = await self.http.get(f"{self.gamma_url}/events/keyset", params=params)
            self.response_count += 1
            if not isinstance(data, dict) or not isinstance(data.get("events"), list):
                break
            results.extend(item for item in data["events"] if isinstance(item, dict))
            cursor = data.get("next_cursor")
            if not cursor:
                break
            if page == MAX_KEYSET_PAGES - 1:
                self.degraded_reason = (
                    f"Polymarket tag {tag_id} exceeded {MAX_KEYSET_PAGES} keyset pages"
                )
        return results

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

    def _parse_gamma_event(self, event: dict[str, Any], sport: Sport) -> ScrapedEvent | None:
        markets = event.get("markets") or []
        title = event.get("title") or ""
        slug = event.get("slug") or event.get("id", "")
        url = f"https://polymarket.com/event/{slug}"
        home, away = self._extract_teams(title, [])
        if not home or not away:
            return None
        market_outcomes: list[MarketOutcome] = []
        start_time = None
        for market in markets:
            if not isinstance(market, dict) or market.get("closed") or not market.get("active", True):
                continue
            if market.get("sportsMarketType") not in (None, "moneyline") or market.get("acceptingOrders") is False:
                continue
            outcomes, prices = self._parse_outcomes_prices(market)
            token_ids = self._parse_token_ids(market)
            if not outcomes or len(outcomes) != len(prices):
                continue
            try:
                yes_index = [str(x).lower() for x in outcomes].index("yes")
            except ValueError:
                continue
            group = str(market.get("groupItemTitle") or "")
            if group.lower().startswith("draw"):
                name = "Draw"
            elif group.casefold() == home.casefold():
                name = home
            elif group.casefold() == away.casefold():
                name = away
            else:
                continue
            price = prices[yes_index]
            if not 0 < price < 1:
                continue
            market_outcomes.append(
                MarketOutcome(
                    name=name,
                    decimal_odds=1.0 / price,
                    implied_prob=price,
                    liquidity_usd=self._safe_float(market.get("liquidity")),
                    token_id=token_ids[yes_index] if yes_index < len(token_ids) else None,
                    selection_id=str(market.get("id") or ""),
                    url=url,
                    raw={
                        "gamma_price": price,
                        "fee_rate": self._market_fee_rate(market),
                    },
                )
            )
            start_time = start_time or self._parse_datetime(
                market.get("gameStartTime") or market.get("eventStartTime")
            )
        expected = 3 if any(x.name == "Draw" for x in market_outcomes) else 2
        unique = {x.name.casefold(): x for x in market_outcomes}
        if len(unique) != expected or home.casefold() not in unique or away.casefold() not in unique:
            return None
        return ScrapedEvent(
            platform=Platform.POLYMARKET,
            sport=sport,
            event_id=str(event.get("id") or slug),
            home_team=home,
            away_team=away,
            league=event.get("seriesSlug") or sport.value,
            start_time=start_time,
            market_type="1x2" if expected == 3 else "moneyline",
            outcomes=list(unique.values()),
            url=url,
            is_live=bool(event.get("live")),
            raw={"game_id": event.get("gameId")},
        )

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
                # BUY returns the lowest ask: the executable price paid to acquire
                # the outcome token. SELL returns the bid and would overstate odds.
                body = [{"token_id": tid, "side": "BUY"} for tid in batch]
                prices_data = await self.http.post(f"{self.clob_url}/prices", json=body)
                self.response_count += 1
                if isinstance(prices_data, dict):
                    for tid, price_value in prices_data.items():
                        if tid in token_map:
                            _, outcome = token_map[tid]
                            price = self._safe_float(
                                price_value.get("BUY") if isinstance(price_value, dict) else price_value
                            )
                            if 0 < price < 1:
                                outcome.decimal_odds = 1.0 / price
                                outcome.implied_prob = price
                                outcome.raw["clob_price"] = price
            except Exception:
                logger.debug("CLOB price enrichment failed for batch %d", i)

    @staticmethod
    def _market_fee_rate(market: dict[str, Any]) -> float:
        if market.get("feesEnabled") is not True:
            return 0.0
        schedule = market.get("feeSchedule") or market.get("fee_schedule") or {}
        rate = PolymarketScraper._safe_float(
            schedule.get("rate") if isinstance(schedule, dict) else None
        )
        # Official sports taker rate. Use it when a fee-enabled market omits the
        # expanded schedule from Gamma.
        return rate if rate > 0 else 0.03

    @staticmethod
    def _parse_outcomes_prices(market: dict[str, Any]) -> tuple[list[str], list[float]]:
        outcomes_raw = market.get("outcomes", "[]")
        prices_raw = market.get("outcomePrices", "[]")
        try:
            outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw or []
            raw_prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw or []
            return list(outcomes), [float(p) for p in raw_prices]
        except (json.JSONDecodeError, TypeError, ValueError):
            return [], []

    @staticmethod
    def _parse_token_ids(market: dict[str, Any]) -> list[str]:
        clob_ids = market.get("clobTokenIds", "[]")
        try:
            if isinstance(clob_ids, str):
                return json.loads(clob_ids)
            return list(clob_ids or [])
        except (json.JSONDecodeError, TypeError):
            return []

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
