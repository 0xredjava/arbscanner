import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from config.settings import Settings
from models.odds import MarketOutcome, Platform, ScrapedEvent, Sport
from orchestrator import ArbOrchestrator
from scrapers.base import SourceStatusError
from scrapers.bcgame import BCGameScraper
from scrapers.cloudbet import CloudbetScraper
from scrapers.polymarket import MAX_KEYSET_PAGES, PolymarketScraper
from scrapers.shuffle import ShuffleScraper
from scrapers.thunderpick import ThunderpickScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def settings():
    return Settings(_env_file=None)


def test_cloudbet_documented_market_shape():
    scraper = CloudbetScraper(settings(), None, None)
    events = scraper._parse_response(load("cloudbet_events.json"), Sport.NBA)
    assert len(events) == 1
    assert [outcome.name for outcome in events[0].outcomes] == ["Miami Heat", "Los Angeles Lakers"]


def test_cloudbet_current_competition_response_and_league_filter():
    scraper = CloudbetScraper(settings(), None, None)
    fixture_event = load("cloudbet_events.json")["events"][0]
    data = {
        "competitions": [
            {
                "name": "WNBA",
                "key": "basketball-usa-wnba",
                "events": [fixture_event],
            },
            {
                "name": "NBA",
                "key": "basketball-usa-nba",
                "events": [fixture_event],
            },
            {
                "name": "Simulated Reality League NBA",
                "key": "basketball-simulated-reality-league-nba",
                "events": [fixture_event],
            },
        ]
    }

    events = scraper._parse_response(data, Sport.NBA, "basketball-usa-nba")

    assert len(events) == 1
    assert events[0].league == "NBA"
    assert len(scraper._parse_response(data, Sport.NBA)) == 2


def test_spt_provider_parses_three_way_market():
    fixture = load("spt_event.json")
    scraper = BCGameScraper(settings(), None, None)
    event = scraper._parse_event(fixture["event_id"], fixture["event"], fixture["tournaments"])
    assert event is not None
    assert event.market_type == "1x2"
    assert [outcome.name for outcome in event.outcomes] == ["Annapolis Blues FC", "Draw", "Virginia Beach United FC"]


def test_shuffle_fractional_prices_and_home_away_order():
    scraper = ShuffleScraper(settings(), None, None)
    events = scraper._parse_competitions(load("shuffle_competitions.json"), Sport.SOCCER)
    assert len(events) == 1
    assert events[0].home_team == "Spain"
    assert {outcome.name: outcome.decimal_odds for outcome in events[0].outcomes} == {
        "Saudi Arabia": 28.0,
        "Spain": 1.1,
        "Draw": 11.0,
    }


def test_thunderpick_native_shape_and_string_regression():
    scraper = ThunderpickScraper(settings(), None, None)
    events = scraper._parse_response(load("thunderpick_matches.json"))
    assert len(events) == 1
    assert events[0].market_type == "1x2"
    assert scraper._parse_response("not a dictionary") == []
    assert scraper._parse_response({"data": {"upcoming": ["not a dictionary"]}}) == []


def test_polymarket_combines_binary_yes_tokens_into_1x2():
    scraper = PolymarketScraper(settings(), None, None)
    event = scraper._parse_gamma_event(load("polymarket_event.json"), Sport.SOCCER)
    assert event is not None
    assert event.event_id == "202605"
    assert event.market_type == "1x2"
    assert {outcome.name for outcome in event.outcomes} == {
        "New England Revolution", "Houston Dynamo", "Draw"
    }
    assert {outcome.token_id for outcome in event.outcomes} == {"home-yes", "away-yes", "draw-yes"}


class KeysetHttp:
    def __init__(self, page_count):
        self.page_count = page_count
        self.calls = 0

    async def get(self, _url, params=None):
        self.calls += 1
        return {
            "events": [{"id": f"event-{self.calls}"}],
            "next_cursor": (
                f"cursor-{self.calls}" if self.calls < self.page_count else None
            ),
        }


def test_polymarket_keyset_completes_six_pages_without_degradation():
    http = KeysetHttp(page_count=6)
    scraper = PolymarketScraper(settings(), http, None)

    events = asyncio.run(scraper._fetch_events_keyset(100350))

    assert len(events) == 6
    assert scraper.response_count == 6
    assert scraper.degraded_reason is None


def test_polymarket_keyset_reports_bounded_truncation():
    http = KeysetHttp(page_count=MAX_KEYSET_PAGES + 1)
    scraper = PolymarketScraper(settings(), http, None)

    events = asyncio.run(scraper._fetch_events_keyset(100350))

    assert len(events) == MAX_KEYSET_PAGES
    assert scraper.degraded_reason == (
        f"Polymarket tag 100350 exceeded {MAX_KEYSET_PAGES} keyset pages"
    )


def future_event():
    return ScrapedEvent(
        platform=Platform.THUNDERPICK,
        sport=Sport.NBA,
        event_id="future",
        home_team="Home",
        away_team="Away",
        league="League",
        start_time=datetime.now(timezone.utc) + timedelta(hours=2),
        market_type="moneyline",
        outcomes=[MarketOutcome("Home", 2.0), MarketOutcome("Away", 2.0)],
    )


class FakeScraper:
    platform = Platform.THUNDERPICK
    source_type = "api"
    fetch_method = "api"
    response_count = 0
    data_timestamp = None
    degraded_reason = None

    def __init__(self, value):
        self.value = value

    async def fetch_events(self):
        if self.value == "degraded":
            self.degraded_reason = "partial source data"
            return [future_event()]
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def test_platform_health_states_are_honest():
    orchestrator = ArbOrchestrator(settings())
    events, ok = asyncio.run(orchestrator._fetch_platform(FakeScraper([future_event()])))
    assert events and ok["status"] == "ok"
    _, empty = asyncio.run(orchestrator._fetch_platform(FakeScraper([])))
    assert empty["status"] == "empty"
    _, unavailable = asyncio.run(
        orchestrator._fetch_platform(FakeScraper(SourceStatusError("unavailable", "no source")))
    )
    assert unavailable["status"] == "unavailable"
    _, degraded = asyncio.run(orchestrator._fetch_platform(FakeScraper("degraded")))
    assert degraded["status"] == "degraded"
    request = httpx.Request("GET", "https://example.test")
    response = httpx.Response(403, request=request)
    blocked_error = httpx.HTTPStatusError("blocked", request=request, response=response)
    _, blocked = asyncio.run(orchestrator._fetch_platform(FakeScraper(blocked_error)))
    assert blocked["status"] == "blocked"
    _, failed = asyncio.run(orchestrator._fetch_platform(FakeScraper(ValueError("bad parser"))))
    assert failed["status"] == "failed"
