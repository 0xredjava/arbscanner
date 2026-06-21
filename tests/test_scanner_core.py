from datetime import datetime, timedelta, timezone

from calculator.arb_calculator import ArbCalculator
from matcher.event_matcher import EventMatcher
from models.odds import MarketOutcome, Platform, ScrapedEvent, Sport
from normalizer.odds_normalizer import OddsNormalizer


def event(platform, home, away, outcomes, market_type="moneyline", sport=Sport.NBA, start_time=None, league="nba"):
    return ScrapedEvent(
        platform=platform,
        sport=sport,
        event_id=f"{platform.value}-{home}-{away}",
        home_team=home,
        away_team=away,
        league=league,
        start_time=start_time or datetime(2026, 1, 1, tzinfo=timezone.utc),
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


def test_does_not_match_unrelated_teams_from_same_league():
    matcher = EventMatcher(threshold=75)
    matches = matcher.match_events(
        [
            event(Platform.BCGAME, "Athletics", "Los Angeles Angels", [("Athletics", 1.7), ("Los Angeles Angels", 2.1)], sport=Sport.MLB, league="MLB"),
            event(Platform.TGCASINO, "Los Angeles Dodgers", "Baltimore Orioles", [("Los Angeles Dodgers", 1.5), ("Baltimore Orioles", 2.9)], sport=Sport.MLB, league="MLB"),
        ]
    )

    assert matches == []


def test_does_not_match_rematches_outside_time_window():
    matcher = EventMatcher(threshold=75, max_time_diff_minutes=120)
    first = datetime(2026, 1, 1, tzinfo=timezone.utc)
    matches = matcher.match_events(
        [
            event(Platform.BCGAME, "Team A", "Team B", [("Team A", 2.0), ("Team B", 2.0)], start_time=first),
            event(Platform.TGCASINO, "Team A", "Team B", [("Team A", 2.0), ("Team B", 2.0)], start_time=first + timedelta(hours=3)),
        ]
    )

    assert matches == []


def test_rejects_cross_match_when_all_best_legs_are_one_platform():
    matcher = EventMatcher(threshold=75)
    matches = matcher.match_events(
        [
            event(Platform.BCGAME, "Team A", "Team B", [("Team A", 2.2), ("Team B", 2.2)]),
            event(Platform.TGCASINO, "Team A", "Team B", [("Team A", 1.7), ("Team B", 1.7)]),
        ]
    )
    calculator = ArbCalculator(min_profit_pct=1, bankroll=100, default_fee_pct=0, slippage_pct=0)

    assert calculator.find_arbitrages(matches) == []


def test_swapped_fixture_order_keeps_outcomes_aligned():
    matcher = EventMatcher(threshold=75)
    matches = matcher.match_events(
        [
            event(Platform.CLOUDBET, "Team A", "Team B", [("Team A", 2.2), ("Team B", 1.7)]),
            event(Platform.STAKE, "Team B", "Team A", [("Team B", 2.2), ("Team A", 1.7)]),
        ]
    )
    calculator = ArbCalculator(min_profit_pct=1, bankroll=100, default_fee_pct=0, slippage_pct=0)

    opportunities = calculator.find_arbitrages(matches)

    assert len(opportunities) == 1
    assert {leg.outcome_name for leg in opportunities[0].legs} == {"Team A", "Team B"}
    assert {leg.platform for leg in opportunities[0].legs} == {Platform.CLOUDBET, Platform.STAKE}
