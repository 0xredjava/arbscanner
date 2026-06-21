"""Arbitrage detection and stake sizing."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher
from models.odds import (
    ArbitrageOpportunity,
    EventMatch,
    MarketOutcome,
    Platform,
    ScrapedEvent,
    StakeAllocation,
)
from normalizer.odds_normalizer import OddsNormalizer

logger = logging.getLogger("arb_scanner.calculator")


class ArbCalculator:
    def __init__(
        self,
        min_profit_pct: float = 2.0,
        bankroll: float = 1000.0,
        default_fee_pct: float = 2.0,
        slippage_pct: float = 1.0,
        liquidity_buffer_pct: float = 5.0,
    ) -> None:
        self.min_profit_pct = min_profit_pct
        self.bankroll = bankroll
        self.default_fee_pct = default_fee_pct
        self.slippage_pct = slippage_pct
        self.liquidity_buffer_pct = liquidity_buffer_pct
        self.normalizer = OddsNormalizer(default_fee_pct, slippage_pct)
        self.platform_fees = OddsNormalizer.PLATFORM_FEES

    def find_arbitrages(self, matches: list[EventMatch]) -> list[ArbitrageOpportunity]:
        opportunities: list[ArbitrageOpportunity] = []
        for match in matches:
            arb = self._check_match(match)
            if arb:
                opportunities.append(arb)
        opportunities.sort(key=lambda a: a.profit_pct, reverse=True)
        logger.info("Found %d arbitrage opportunities", len(opportunities))
        return opportunities

    def find_intra_platform_arbs(self, events: list[ScrapedEvent]) -> list[ArbitrageOpportunity]:
        """Detect arbs within Polymarket multi-outcome markets (sum of probs < 1)."""
        opportunities: list[ArbitrageOpportunity] = []
        for event in events:
            if len(event.outcomes) < 2:
                continue
            arb = self._check_single_event_arb(event)
            if arb:
                opportunities.append(arb)
        return opportunities

    def _check_match(self, match: EventMatch) -> ArbitrageOpportunity | None:
        """For 2-way markets: find best odds per outcome across platforms."""
        if match.events[0].market_type not in ("moneyline", "1x2", "prediction"):
            return self._check_multi_outcome_match(match)

        required_keys = (
            ("home", "draw", "away")
            if match.events[0].market_type == "1x2"
            else ("yes", "no")
            if match.events[0].market_type == "prediction"
            else ("home", "away")
        )
        best_legs = self._best_odds_per_outcome(match, required_keys)
        if len(best_legs) != len(required_keys):
            return None
        if len({event.platform for _key, _outcome, event in best_legs}) < 2:
            return None

        return self._calculate_arb(
            match_id=match.match_id,
            sport=match.sport,
            event_name=f"{match.home_team} vs {match.away_team}",
            league=match.league,
            market_type=match.events[0].market_type,
            legs=best_legs,
        )

    def _best_odds_per_outcome(
        self, match: EventMatch, required_keys: tuple[str, ...] | None = None
    ) -> list[tuple[str, MarketOutcome, ScrapedEvent]]:
        """Pick highest decimal odds for each distinct outcome across platforms."""
        outcome_buckets: dict[str, list[tuple[MarketOutcome, ScrapedEvent]]] = {}

        for event in match.events:
            direct = (
                self._team_similarity(event.home_team, match.home_team)
                + self._team_similarity(event.away_team, match.away_team)
            )
            swapped = (
                self._team_similarity(event.home_team, match.away_team)
                + self._team_similarity(event.away_team, match.home_team)
            )
            is_swapped = swapped > direct
            for outcome in event.outcomes:
                key = self._outcome_key(outcome.name, event)
                if is_swapped and key in ("home", "away"):
                    key = "away" if key == "home" else "home"
                outcome_buckets.setdefault(key, []).append((outcome, event))

        best: list[tuple[str, MarketOutcome, ScrapedEvent]] = []
        keys = required_keys or tuple(outcome_buckets)
        for key in keys:
            candidates = outcome_buckets.get(key)
            if not candidates:
                continue
            best_pair = max(candidates, key=lambda x: x[0].decimal_odds)
            best.append((key, best_pair[0], best_pair[1]))
        return best

    def _team_similarity(self, a: str, b: str) -> float:
        left = self.normalizer.clean_team_name(a)
        right = self.normalizer.clean_team_name(b)
        if left == right:
            return 100.0
        ratio = SequenceMatcher(None, left, right).ratio() * 100
        token_ratio = SequenceMatcher(
            None, " ".join(sorted(left.split())), " ".join(sorted(right.split()))
        ).ratio() * 100
        return max(ratio, token_ratio)

    def _outcome_key(self, name: str, event: ScrapedEvent) -> str:
        cleaned = self.normalizer.clean_outcome_name(name)
        home = self.normalizer.clean_team_name(event.home_team)
        away = self.normalizer.clean_team_name(event.away_team)

        if cleaned in (home, "home", "1"):
            return "home"
        if cleaned in (away, "away", "2"):
            return "away"
        if cleaned in ("draw", "x", "tie"):
            return "draw"
        if cleaned in ("yes", "no"):
            return cleaned
        return cleaned

    def _check_multi_outcome_match(self, match: EventMatch) -> ArbitrageOpportunity | None:
        best_legs = self._best_odds_per_outcome(match)
        if len(best_legs) < 2:
            return None
        return self._calculate_arb(
            match_id=match.match_id,
            sport=match.sport,
            event_name=f"{match.home_team} vs {match.away_team}",
            league=match.league,
            market_type=match.events[0].market_type,
            legs=best_legs,
        )

    def _check_single_event_arb(self, event: ScrapedEvent) -> ArbitrageOpportunity | None:
        legs = [
            (self._outcome_key(o.name, event), o, event) for o in event.outcomes
        ]
        return self._calculate_arb(
            match_id=event.event_id,
            sport=event.sport,
            event_name=event.display_name,
            league=event.league,
            market_type=event.market_type,
            legs=legs,
        )

    def _calculate_arb(
        self,
        match_id: str,
        sport,
        event_name: str,
        league: str,
        market_type: str,
        legs: list[tuple[str, MarketOutcome, ScrapedEvent]],
    ) -> ArbitrageOpportunity | None:
        if len(legs) < 2:
            return None

        fee_adjusted_probs: list[float] = []
        allocations: list[StakeAllocation] = []
        warnings: list[str] = []
        min_liquidity: float | None = None

        for _key, outcome, event in legs:
            fee = self.platform_fees.get(event.platform, self.default_fee_pct)
            effective_odds = outcome.decimal_odds * (1 - fee / 100) * (1 - self.slippage_pct / 100)
            if effective_odds <= 1:
                return None
            fee_adjusted_probs.append(1.0 / effective_odds)

            if outcome.liquidity_usd is not None:
                if min_liquidity is None:
                    min_liquidity = outcome.liquidity_usd
                else:
                    min_liquidity = min(min_liquidity, outcome.liquidity_usd)

        total_implied = sum(fee_adjusted_probs)
        if total_implied >= 1.0:
            return None

        profit_pct = (1.0 / total_implied - 1.0) * 100
        if profit_pct < self.min_profit_pct:
            return None

        total_stake = self.bankroll
        guaranteed_return = total_stake / total_implied

        for (_key, outcome, event), prob in zip(legs, fee_adjusted_probs):
            fee = self.platform_fees.get(event.platform, self.default_fee_pct)
            stake = guaranteed_return * prob
            effective_odds = outcome.decimal_odds * (1 - fee / 100)
            allocations.append(
                StakeAllocation(
                    platform=event.platform,
                    outcome_name=outcome.name,
                    decimal_odds=outcome.decimal_odds,
                    stake=stake,
                    potential_return=stake * effective_odds,
                    url=outcome.url or event.url,
                    fee_pct=fee,
                )
            )

        if min_liquidity is not None:
            max_stake = min(min_liquidity * (1 - self.liquidity_buffer_pct / 100), total_stake)
            if max_stake < total_stake * 0.1:
                warnings.append(f"Low liquidity: ${min_liquidity:.0f} available")

        if any(a.platform == Platform.POLYMARKET for a in allocations):
            warnings.append("Polymarket: verify CLOB spread and settlement rules")

        return ArbitrageOpportunity(
            match_id=match_id,
            sport=sport,
            event_name=event_name,
            league=league,
            market_type=market_type,
            profit_pct=profit_pct,
            total_stake=total_stake,
            guaranteed_return=guaranteed_return,
            guaranteed_profit=guaranteed_return - total_stake,
            legs=allocations,
            detected_at=datetime.now(timezone.utc),
            min_liquidity_usd=min_liquidity,
            warnings=warnings,
        )
