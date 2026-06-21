"""Shuffle public sports GraphQL adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from models.odds import MarketOutcome, Platform, ScrapedEvent, Sport
from scrapers.base import BaseScraper

SPORTS: dict[str, tuple[str, Sport]] = {
    "soccer": ("SOCCER", Sport.SOCCER),
    "nba": ("BASKETBALL", Sport.NBA),
    "tennis": ("TENNIS", Sport.TENNIS),
    "nfl": ("AMERICAN_FOOTBALL", Sport.NFL),
    "nhl": ("ICE_HOCKEY", Sport.NHL),
    "mlb": ("BASEBALL", Sport.MLB),
}

QUERY = """query GetSportsCompetitions($first: Int, $cursor: String, $sports: Sports, $categoryId: String, $searchType: SportsSearchType!, $fixtureFirst: Int, $language: Language, $prioritizedMarketTypeId: String, $sportsGroupRulesId: String) {
  sportsCompetitions: sportsCompetitionsV2(first: $first cursor: $cursor sports: $sports categoryId: $categoryId searchType: $searchType fixtureFirst: $fixtureFirst language: $language prioritizedMarketTypeId: $prioritizedMarketTypeId sportsGroupRulesId: $sportsGroupRulesId)
}"""


class ShuffleScraper(BaseScraper):
    platform = Platform.SHUFFLE
    fee_pct = 1.0
    source_type = "graphql"
    fetch_method = "graphql"

    async def fetch_events(self) -> list[ScrapedEvent]:
        results: list[ScrapedEvent] = []
        for watched in self.settings.sports_list:
            config = SPORTS.get(watched)
            if not config:
                continue
            cursor: str | None = None
            for page in range(5):
                payload = {
                    "operationName": "GetSportsCompetitions",
                    "variables": {
                        "first": 10,
                        "fixtureFirst": 10,
                        "cursor": cursor,
                        "language": "en",
                        "searchType": "FEATURED",
                        "sports": config[0],
                        "prioritizedMarketTypeId": None,
                    },
                    "query": QUERY,
                }
                data = await self.http.post(self.settings.shuffle_sports_graphql_url, json=payload)
                self.response_count += 1
                envelope = data.get("data") if isinstance(data, dict) else None
                competitions = envelope.get("sportsCompetitions") if isinstance(envelope, dict) else None
                if not isinstance(competitions, dict):
                    break
                results.extend(self._parse_competitions(competitions, config[1]))
                cursor = competitions.get("nextCursor")
                if not cursor:
                    break
                if page == 4:
                    self.degraded_reason = f"Shuffle {watched} pagination exceeded five pages"
        deduped = {event.event_id: event for event in results}
        return list(deduped.values())

    def _parse_competitions(self, data: Any, sport: Sport) -> list[ScrapedEvent]:
        if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
            return []
        results: list[ScrapedEvent] = []
        for competition in data["nodes"]:
            if not isinstance(competition, dict):
                continue
            fixtures = competition.get("fixtures") or {}
            for fixture in fixtures.get("nodes") or []:
                parsed = self._parse_fixture(fixture, competition, sport)
                if parsed:
                    results.append(parsed)
        return results

    def _parse_fixture(
        self, fixture: Any, competition: dict[str, Any], sport: Sport
    ) -> ScrapedEvent | None:
        if not isinstance(fixture, dict) or fixture.get("status") != "PREMATCH":
            return None
        competitors = fixture.get("competitors") or []
        if not isinstance(competitors, list) or len(competitors) != 2:
            return None
        home_obj = next((x for x in competitors if isinstance(x, dict) and x.get("isHome") is True), None)
        away_obj = next((x for x in competitors if isinstance(x, dict) and x.get("isHome") is False), None)
        if not home_obj or not away_obj:
            return None
        market = ((fixture.get("defaultMarketsInfo") or {}).get("defaultMarket") or {})
        display = market.get("display") or {}
        names: dict[str, str] = {}
        for group in display.get("selectionGroups") or []:
            if not isinstance(group, dict):
                continue
            for selection in group.get("selections") or []:
                if isinstance(selection, dict):
                    names[str(selection.get("id"))] = str(selection.get("fullName") or selection.get("name") or "")
        outcomes: list[MarketOutcome] = []
        for odds_market in market.get("odds") or []:
            if not isinstance(odds_market, dict) or odds_market.get("status") != "OPEN" or odds_market.get("inPlay"):
                continue
            candidate: list[MarketOutcome] = []
            for selection in odds_market.get("selections") or []:
                if not isinstance(selection, dict) or selection.get("status") != "TRADING":
                    continue
                sid = str(selection.get("id") or "")
                try:
                    price = 1 + float(selection.get("oddsNumerator")) / float(selection.get("oddsDenominator"))
                except (TypeError, ValueError, ZeroDivisionError):
                    continue
                if names.get(sid) and price > 1:
                    candidate.append(
                        MarketOutcome(
                            name=names[sid], decimal_odds=price, selection_id=sid, raw={"probability": selection.get("probability")}
                        )
                    )
            if len(candidate) in (2, 3):
                outcomes = candidate
                break
        if len(outcomes) not in (2, 3):
            return None
        category = competition.get("category") or {}
        slug_parts = [
            str(category.get("sports") or sport.value).lower().replace("_", "-"),
            str(category.get("slug") or ""),
            str(competition.get("slug") or ""),
            str(fixture.get("slug") or ""),
        ]
        url = "https://shuffle.com/sports/" + "/".join(x for x in slug_parts if x)
        return ScrapedEvent(
            platform=self.platform,
            sport=sport,
            event_id=str(fixture.get("id") or ""),
            home_team=str(home_obj.get("displayName") or ""),
            away_team=str(away_obj.get("displayName") or ""),
            league=str(competition.get("name") or ""),
            start_time=self._datetime(fixture.get("startTime")),
            market_type="1x2" if len(outcomes) == 3 else "moneyline",
            outcomes=outcomes,
            url=url,
            raw={"provider": fixture.get("provider"), "market_type": display.get("typeId")},
        )

    @staticmethod
    def _datetime(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
