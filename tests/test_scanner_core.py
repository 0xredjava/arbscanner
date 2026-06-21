from datetime import datetime, timedelta, timezone

from calculator.arb_calculator import ArbCalculator
from matcher.event_matcher import EventMatcher
from models.odds import MarketOutcome, OrderBookLevel, Platform, ScrapedEvent, Sport
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


def test_closest_markets_explains_non_profitable_match():
    matcher = EventMatcher(threshold=75)
    matches = matcher.match_events(
        [
            event(Platform.CLOUDBET, "Team A", "Team B", [("Team A", 1.9), ("Team B", 1.8)]),
            event(Platform.THUNDERPICK, "Team A", "Team B", [("Team A", 1.8), ("Team B", 1.9)]),
        ]
    )
    calculator = ArbCalculator(min_profit_pct=2, bankroll=100)

    comparisons = calculator.closest_markets(matches)

    assert len(comparisons) == 1
    assert comparisons[0]["margin_pct"] < 0
    assert comparisons[0]["break_even_gap_pct"] > 0


def test_polymarket_taker_fee_reduces_effective_odds():
    calculator = ArbCalculator(default_fee_pct=0, slippage_pct=0)
    poly_event = event(
        Platform.POLYMARKET,
        "Team A",
        "Team B",
        [("Team A", 2.0), ("Team B", 2.0)],
    )
    poly_event.outcomes[0].raw["fee_rate"] = 0.03

    effective, cost_pct = calculator._effective_odds(
        poly_event.outcomes[0], poly_event
    )

    assert round(effective, 6) == round(1 / (0.5 + 0.03 * 0.5 * 0.5), 6)
    assert cost_pct > 0


def londrina_match(away_price=0.18, away_depth=10_000, quote_time=None):
    quote_time = quote_time or datetime.now(timezone.utc)
    sportsbook = event(
        Platform.THUNDERPICK,
        "Cuiaba EC",
        "Londrina EC",
        [("Cuiaba EC", 1.89), ("Draw", 3.0), ("Londrina EC", 4.0)],
        market_type="1x2",
        sport=Sport.SOCCER,
        league="Brazil Serie B",
    )
    polymarket = event(
        Platform.POLYMARKET,
        "Cuiaba EC",
        "Londrina EC",
        [("Cuiaba EC", 1.7), ("Draw", 1 / 0.26), ("Londrina EC", 1 / away_price)],
        market_type="1x2",
        sport=Sport.SOCCER,
        league="brazil-serie-b",
    )
    for outcome in polymarket.outcomes:
        price = 0.26 if outcome.name == "Draw" else away_price if outcome.name == "Londrina EC" else 0.60
        size = away_depth if outcome.name == "Londrina EC" else 10_000
        outcome.ask_levels = [OrderBookLevel(price=price, size=size)]
        outcome.quote_fetched_at = quote_time
        outcome.token_id = f"token-{outcome.name}"
        outcome.raw["minimum_order_size"] = 5
    return EventMatcher(threshold=75).match_events([sportsbook, polymarket])


def test_polymarket_eighteen_cent_leg_reconciles_cost_shares_and_payout():
    opportunity = ArbCalculator(
        min_profit_pct=1, bankroll=1000, liquidity_buffer_pct=0
    ).find_arbitrages(londrina_match())[0]
    leg = next(item for item in opportunity.legs if item.outcome_name == "Londrina EC")

    assert leg.price == 0.18
    assert abs(leg.stake / 0.18 - (leg.shares or 0)) < 0.06
    assert leg.net_payout == leg.shares
    assert round(162.14 / 0.18, 2) == 900.78
    assert opportunity.guaranteed_return == min(item.net_payout for item in opportunity.legs)


def test_polymarket_depth_scales_down_entire_opportunity():
    opportunity = ArbCalculator(
        min_profit_pct=1, bankroll=1000, liquidity_buffer_pct=5
    ).find_arbitrages(londrina_match(away_depth=200))[0]

    assert opportunity.total_stake < 1000
    away = next(item for item in opportunity.legs if item.outcome_name == "Londrina EC")
    assert (away.shares or 0) <= 190


def test_expired_polymarket_quote_is_rejected():
    stale = datetime.now(timezone.utc) - timedelta(minutes=2)
    calculator = ArbCalculator(min_profit_pct=1, bankroll=1000, quote_ttl_seconds=45)

    assert calculator.find_arbitrages(londrina_match(quote_time=stale)) == []


def test_opportunity_fingerprint_is_stable_across_observations():
    calculator = ArbCalculator(min_profit_pct=1, bankroll=1000, liquidity_buffer_pct=0)
    first = calculator.find_arbitrages(londrina_match())[0]
    second = calculator.find_arbitrages(londrina_match())[0]

    assert first.fingerprint == second.fingerprint
    assert first.detected_at != second.detected_at


def test_geography_is_not_implicitly_brazil_only():
    brazil = event(Platform.THUNDERPICK, "A", "B", [("A", 2), ("B", 2)], league="Brazil Serie B")
    england = event(Platform.THUNDERPICK, "C", "D", [("C", 2), ("D", 2)], league="Premier League")

    assert brazil.country == "Brazil"
    assert england.country == "England"
