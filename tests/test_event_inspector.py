from services.scan_service import group_event_rows


def test_groups_persisted_outcomes_into_inspectable_events():
    rows = [
        {
            "platform": "cloudbet",
            "sport": "soccer",
            "event_key": "soccer:home|away:20260621:1x2",
            "event_id": "event-1",
            "home_team": "Home",
            "away_team": "Away",
            "league": "League",
            "start_time": "2026-06-21T20:00:00+00:00",
            "market_type": "1x2",
            "outcome_name": "home",
            "decimal_odds": 2.1,
            "implied_prob": 1 / 2.1,
            "fee_adjusted_prob": 1 / 2.1,
            "liquidity_usd": None,
            "url": "https://example.test/event-1",
        },
        {
            "platform": "cloudbet",
            "sport": "soccer",
            "event_key": "soccer:home|away:20260621:1x2",
            "event_id": "event-1",
            "home_team": "Home",
            "away_team": "Away",
            "league": "League",
            "start_time": "2026-06-21T20:00:00+00:00",
            "market_type": "1x2",
            "outcome_name": "away",
            "decimal_odds": 3.5,
            "implied_prob": 1 / 3.5,
            "fee_adjusted_prob": 1 / 3.5,
            "liquidity_usd": None,
            "url": "https://example.test/event-1",
        },
    ]

    events = group_event_rows(rows)

    assert len(events) == 1
    assert events[0]["platform"] == "cloudbet"
    assert [outcome["name"] for outcome in events[0]["outcomes"]] == [
        "home",
        "away",
    ]
