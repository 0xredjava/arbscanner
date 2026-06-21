"""Thunderpick public same-origin REST adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from models.odds import MarketOutcome, Platform, ScrapedEvent, Sport
from scrapers.base import BaseScraper

GAMES: dict[str, tuple[int, Sport]] = {
    "soccer": (10, Sport.SOCCER),
    "nba": (11, Sport.NBA),
    "mlb": (13, Sport.MLB),
    "nhl": (14, Sport.NHL),
    "tennis": (15, Sport.TENNIS),
    "mma": (16, Sport.MMA),
    "nfl": (18, Sport.NFL),
}
SPORT_BY_GAME = {game_id: sport for game_id, sport in GAMES.values()}


class ThunderpickScraper(BaseScraper):
    platform = Platform.THUNDERPICK
    fee_pct = 1.0
    source_type = "api"

    async def fetch_events(self) -> list[ScrapedEvent]:
        game_ids = [GAMES[name][0] for name in self.settings.sports_list if name in GAMES]
        if not game_ids:
            return []
        data = await self.http.post(
            f"{self.settings.thunderpick_api_url.rstrip('/')}/matches",
            json={"gameIds": game_ids, "competitionId": None, "country": None},
            headers={"Accept": "application/json"},
        )
        self.response_count = 1
        return self._parse_response(data)

    def _parse_response(self, data: Any) -> list[ScrapedEvent]:
        if not isinstance(data, dict):
            return []
        envelope = data.get("data") or {}
        upcoming = envelope.get("upcoming") if isinstance(envelope, dict) else None
        if not isinstance(upcoming, list):
            return []
        return [parsed for item in upcoming if (parsed := self._parse_match(item))]

    def _parse_match(self, match: Any) -> ScrapedEvent | None:
        if not isinstance(match, dict) or match.get("isLive") is True:
            return None
        sport = SPORT_BY_GAME.get(match.get("gameId"))
        teams, market = match.get("teams"), match.get("market")
        if not sport or not isinstance(teams, dict) or not isinstance(market, dict) or market.get("status") != 1:
            return None
        home_obj, away_obj = teams.get("home"), teams.get("away")
        if not isinstance(home_obj, dict) or not isinstance(away_obj, dict):
            return None
        outcomes: list[MarketOutcome] = []
        for key in ("home", "draw", "away"):
            selection = market.get(key)
            if not isinstance(selection, dict) or selection.get("status") != 1:
                continue
            try:
                price = float(selection.get("odds"))
            except (TypeError, ValueError):
                continue
            if price > 1 and selection.get("name"):
                outcomes.append(
                    MarketOutcome(
                        name=str(selection["name"]),
                        decimal_odds=price,
                        selection_id=str(selection.get("id") or ""),
                        raw={"type": key},
                    )
                )
        if len(outcomes) not in (2, 3):
            return None
        competition = match.get("competition") or {}
        event_id = str(match.get("id") or "")
        return ScrapedEvent(
            platform=self.platform,
            sport=sport,
            event_id=event_id,
            home_team=str(home_obj.get("name") or ""),
            away_team=str(away_obj.get("name") or ""),
            league=str(competition.get("name") or ""),
            start_time=self._datetime(match.get("startTime")),
            market_type="1x2" if len(outcomes) == 3 else "moneyline",
            outcomes=outcomes,
            url=f"https://thunderpick.io/match/{event_id}",
            raw={"market_id": market.get("id"), "game_id": match.get("gameId")},
        )

    @staticmethod
    def _datetime(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
