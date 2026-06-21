"""Parser for the anonymous sportsbook-provider feed used by BC.Game and TG.Casino."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from models.odds import MarketOutcome, Platform, ScrapedEvent, Sport
from scrapers.base import BaseScraper

SPORTS: dict[str, tuple[Sport, tuple[str, ...]]] = {
    "1": (Sport.SOCCER, ("1",)),
    "2": (Sport.NBA, ("219", "186", "1")),
    "5": (Sport.TENNIS, ("186", "1")),
    "16": (Sport.NFL, ("219", "186", "1")),
    "4": (Sport.NHL, ("186", "1")),
    "3": (Sport.MLB, ("251", "186", "1")),
    "117": (Sport.MMA, ("186", "1")),
}

WATCHED = {
    Sport.SOCCER: "soccer",
    Sport.NBA: "nba",
    Sport.TENNIS: "tennis",
    Sport.NFL: "nfl",
    Sport.NHL: "nhl",
    Sport.MLB: "mlb",
    Sport.MMA: "mma",
}


class SptFeedScraper(BaseScraper):
    source_type = "api"
    feed_url: str
    brand_id: str
    locale = "en"
    public_url: str

    async def fetch_events(self) -> list[ScrapedEvent]:
        base = f"{self.feed_url.rstrip('/')}/api/v4/prematch/brand/{self.brand_id}/{self.locale}"
        manifest = await self.http.get(f"{base}/0")
        self.response_count = 1
        if not isinstance(manifest, dict):
            return []
        versions = list(manifest.get("top_events_versions") or []) + list(
            manifest.get("rest_events_versions") or []
        )
        events: dict[str, Any] = {}
        tournaments: dict[str, Any] = {}
        latest_generated = manifest.get("generated")
        for version in versions:
            chunk = await self.http.get(f"{base}/{version}")
            self.response_count += 1
            if not isinstance(chunk, dict):
                continue
            events.update(chunk.get("events") or {})
            tournaments.update(chunk.get("tournaments") or {})
            latest_generated = max(latest_generated or 0, chunk.get("generated") or 0)
        if latest_generated:
            self.data_timestamp = datetime.fromtimestamp(float(latest_generated) / 1000, tz=timezone.utc)
        watched = set(self.settings.sports_list)
        results: list[ScrapedEvent] = []
        for event_id, event in events.items():
            parsed = self._parse_event(str(event_id), event, tournaments)
            if parsed and WATCHED.get(parsed.sport) in watched:
                results.append(parsed)
        return results

    def _parse_event(
        self, event_id: str, event: Any, tournaments: dict[str, Any]
    ) -> ScrapedEvent | None:
        if not isinstance(event, dict):
            return None
        desc, state, markets = event.get("desc"), event.get("state"), event.get("markets")
        if not isinstance(desc, dict) or not isinstance(state, dict) or not isinstance(markets, dict):
            return None
        if desc.get("type") != "match" or desc.get("virtual") is True or state.get("status") != 0:
            return None
        source_sport = str(desc.get("sport") or "")
        sport_config = SPORTS.get(source_sport)
        competitors = desc.get("competitors") or []
        if not sport_config or not isinstance(competitors, list) or len(competitors) != 2:
            return None
        home, away = str(competitors[0].get("name") or ""), str(competitors[1].get("name") or "")
        if not home or not away:
            return None
        market_id = next((mid for mid in sport_config[1] if isinstance(markets.get(mid), dict)), None)
        market = markets.get(market_id) if market_id else None
        if not isinstance(market, dict):
            return None
        selections = market.get("")
        if not isinstance(selections, dict):
            return None
        names = {"1": home, "2": "Draw", "3": away, "4": home, "5": away}
        expected = ("1", "2", "3") if market_id == "1" else ("4", "5")
        outcomes: list[MarketOutcome] = []
        for outcome_id in expected:
            raw = selections.get(outcome_id)
            if not isinstance(raw, dict):
                continue
            try:
                price = float(raw.get("k"))
            except (TypeError, ValueError):
                continue
            if price > 1:
                outcomes.append(
                    MarketOutcome(
                        name=names[outcome_id],
                        decimal_odds=price,
                        selection_id=f"{event_id}:{market_id}:{outcome_id}",
                        url=f"{self.public_url}/{desc.get('slug') or ''}",
                        raw={"market_id": market_id, "outcome_id": outcome_id},
                    )
                )
        if len(outcomes) != len(expected):
            return None
        tournament = tournaments.get(str(desc.get("tournament"))) or {}
        scheduled = desc.get("scheduled")
        start_time = (
            datetime.fromtimestamp(float(scheduled), tz=timezone.utc)
            if isinstance(scheduled, (int, float))
            else None
        )
        return ScrapedEvent(
            platform=self.platform,
            sport=sport_config[0],
            event_id=event_id,
            home_team=home,
            away_team=away,
            league=str(tournament.get("name") or desc.get("tournament") or ""),
            start_time=start_time,
            market_type="1x2" if len(outcomes) == 3 else "moneyline",
            outcomes=outcomes,
            url=f"{self.public_url}/{desc.get('slug') or ''}",
            raw={"provider": state.get("provider"), "market_id": market_id},
        )
