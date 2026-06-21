from datetime import datetime, timezone

from calculator.arb_calculator import ArbCalculator
from matcher.event_matcher import EventMatcher
from models.odds import MarketOutcome, Platform, ScrapedEvent, Sport
from normalizer.odds_normalizer import OddsNormalizer


def event(platform, home, away, outcomes, market_type="moneyline", sport=Sport.NBA):
    return ScrapedEvent(
        platform=platform,
        sport=sport,
        event_id=f"{platform.value}-{home}-{away}",
        home_team=home,
        away_team=away,
        league="nba",
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        market_type=market_type,
        outcomes=[MarketOutcome(name=name, decimal_odds=odds) for name, odds in outcomes],
    )


def test_normalizes_two_way_moneyline():
    normalizer = OddsNormalizer(default_fee_pct=0, slippage_pct=0)
    records = normalizer.normalize_event(
        event(
            Platform.CLOUDBET,
            "Boston Celtics",
            "Los Angeles Lakers",
            [("Boston Celtics", 2.1), ("Los Angeles Lakers", 1.9)],
        )
    )

    assert len(records) == 2
    assert records[0].outcome_name == "boston celtics"
    assert records[0].american_odds == 110


def test_matches_team_name_variants():
    matcher = EventMatcher(threshold=70)
    matches = matcher.match_events(
        [
            event(Platform.CLOUDBET, "Boston Celtics", "Los Angeles Lakers", [("Boston Celtics", 2.1), ("Los Angeles Lakers", 1.9)]),
            event(Platform.STAKE, "Celtics", "Lakers", [("Celtics", 2.2), ("Lakers", 1.8)]),
        ]
    )

    assert len(matches) == 1
    assert {match.platform for match in matches[0].events} == {Platform.CLOUDBET, Platform.STAKE}


def test_calculates_profitable_cross_platform_arb():
    matcher = EventMatcher(threshold=70)
    matches = matcher.match_events(
        [
            event(Platform.CLOUDBET, "Team A", "Team B", [("Team A", 2.2), ("Team B", 1.7)]),
            event(Platform.STAKE, "Team A", "Team B", [("Team A", 1.7), ("Team B", 2.2)]),
        ]
    )
    calculator = ArbCalculator(min_profit_pct=1, bankroll=100, default_fee_pct=0, slippage_pct=0)

    opportunities = calculator.find_arbitrages(matches)

    assert len(opportunities) == 1
    assert opportunities[0].profit_pct > 1


def test_rejects_non_profitable_market():
    matcher = EventMatcher(threshold=70)
    matches = matcher.match_events(
        [
            event(Platform.CLOUDBET, "Team A", "Team B", [("Team A", 1.8), ("Team B", 1.8)]),
            event(Platform.STAKE, "Team A", "Team B", [("Team A", 1.7), ("Team B", 1.7)]),
        ]
    )
    calculator = ArbCalculator(min_profit_pct=1, bankroll=100, default_fee_pct=0, slippage_pct=0)

    assert calculator.find_arbitrages(matches) == []
