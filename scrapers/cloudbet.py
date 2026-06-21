"""Cloudbet official Feed API adapter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from models.odds import MarketOutcome, Platform, ScrapedEvent, Sport
from scrapers.base import BaseScraper, SourceStatusError

SPORTS: dict[str, tuple[str, Sport, str, str | None]] = {
    "soccer": ("soccer", Sport.SOCCER, "soccer.match_odds", None),
    "nba": ("basketball", Sport.NBA, "basketball.moneyline", "basketball-usa-nba"),
    "tennis": ("tennis", Sport.TENNIS, "tennis.winner", None),
    "nfl": (
        "american-football",
        Sport.NFL,
        "american_football.moneyline",
        "american-football-usa-nfl",
    ),
    "nhl": ("ice-hockey", Sport.NHL, "ice_hockey.moneyline", "ice-hockey-usa-nhl"),
    "mlb": ("baseball", Sport.MLB, "baseball.moneyline", "baseball-usa-mlb"),
}

MARKET_KEYS = {sport: market for _source, sport, market, _competition in SPORTS.values()}


class CloudbetScraper(BaseScraper):
    platform = Platform.CLOUDBET
    fee_pct = 0.0
    source_type = "api"

    async def fetch_events(self) -> list[ScrapedEvent]:
        if not self.settings.cloudbet_api_key:
            raise SourceStatusError("unavailable", "CLOUDBET_API_KEY is not configured")
        headers = {"X-API-Key": self.settings.cloudbet_api_key, "Accept": "application/json"}
        results: list[ScrapedEvent] = []
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=self.settings.max_event_horizon_days)
        for watched in self.settings.sports_list:
            config = SPORTS.get(watched)
            if not config:
                continue
            source_sport, sport, market, competition_key = config
            data = await self.http.get(
                f"{self.settings.cloudbet_api_url.rstrip('/')}/odds/events",
                params={
                    "sport": source_sport,
                    "from": int(start.timestamp()),
                    "to": int(end.timestamp()),
                    "markets": market,
                    "limit": 10000,
                },
                headers=headers,
            )
            self.response_count += 1
            results.extend(self._parse_response(data, sport, competition_key))
        return results

    def _parse_response(
        self, data: Any, sport: Sport, competition_key: str | None = None
    ) -> list[ScrapedEvent]:
        if not isinstance(data, dict):
            return []
        competitions = data.get("competitions")
        if isinstance(competitions, list):
            parsed_events: list[ScrapedEvent] = []
            for competition in competitions:
                if not isinstance(competition, dict):
                    continue
                if competition_key and competition.get("key") != competition_key:
                    continue
                competition_text = (
                    f"{competition.get('name', '')} {competition.get('key', '')}".lower()
                )
                if any(
                    marker in competition_text
                    for marker in ("simulated", "virtual", "esoccer", "-srl", " srl")
                ):
                    continue
                for item in competition.get("events") or []:
                    parsed = self._parse_event(item, sport, competition)
                    if parsed:
                        parsed_events.append(parsed)
            return parsed_events

        # Retain support for the single-event response shape used by fixtures and
        # by older Feed API responses.
        events = data.get("events") or []
        if not isinstance(events, list):
            return []
        return [parsed for item in events if (parsed := self._parse_event(item, sport))]

    def _parse_event(
        self, event: Any, sport: Sport, competition: dict[str, Any] | None = None
    ) -> ScrapedEvent | None:
        if not isinstance(event, dict) or event.get("status") != "TRADING":
            return None
        home_obj, away_obj = event.get("home"), event.get("away")
        if not isinstance(home_obj, dict) or not isinstance(away_obj, dict):
            return None
        home, away = str(home_obj.get("name") or ""), str(away_obj.get("name") or "")
        markets = event.get("markets")
        if not home or not away or not isinstance(markets, dict):
            return None
        market_key = MARKET_KEYS.get(sport)
        market = markets.get(market_key) if market_key else None
        if not isinstance(market, dict):
            return None
        outcomes: list[MarketOutcome] = []
        for submarket in (market.get("submarkets") or {}).values():
            if not isinstance(submarket, dict):
                continue
            candidate: list[MarketOutcome] = []
            for selection in submarket.get("selections") or []:
                if (
                    not isinstance(selection, dict)
                    or selection.get("status") != "SELECTION_ENABLED"
                    or selection.get("side", "BACK") != "BACK"
                ):
                    continue
                raw_name = str(selection.get("outcome") or "").lower()
                name = {"home": home, "away": away, "draw": "Draw"}.get(raw_name, raw_name)
                try:
                    price = float(selection.get("price"))
                except (TypeError, ValueError):
                    continue
                if name and price > 1:
                    candidate.append(MarketOutcome(name=name, decimal_odds=price, raw=selection))
            if len(candidate) in (2, 3):
                outcomes = candidate
                break
        if len(outcomes) not in (2, 3):
            return None
        start_time = self._datetime(event.get("startTime") or event.get("cutoffTime"))
        competition = competition or event.get("competition") or {}
        return ScrapedEvent(
            platform=self.platform,
            sport=sport,
            event_id=str(event.get("id") or event.get("key") or ""),
            home_team=home,
            away_team=away,
            league=str(competition.get("name") or competition.get("key") or ""),
            start_time=start_time,
            market_type="1x2" if len(outcomes) == 3 else "moneyline",
            outcomes=outcomes,
            url="https://www.cloudbet.com/en/sports",
            raw={"status": event.get("status"), "market": market_key},
        )

    @staticmethod
    def _datetime(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
