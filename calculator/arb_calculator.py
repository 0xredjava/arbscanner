"""Arbitrage detection and stake sizing."""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import datetime, timedelta, timezone
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
        default_fee_pct: float = 0.0,
        slippage_pct: float = 0.0,
        liquidity_buffer_pct: float = 5.0,
        quote_aging_seconds: int = 20,
        quote_ttl_seconds: int = 45,
    ) -> None:
        self.min_profit_pct = min_profit_pct
        self.bankroll = bankroll
        self.default_fee_pct = default_fee_pct
        self.slippage_pct = slippage_pct
        self.liquidity_buffer_pct = liquidity_buffer_pct
        self.quote_aging_seconds = quote_aging_seconds
        self.quote_ttl_seconds = quote_ttl_seconds
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

    def closest_markets(
        self, matches: list[EventMatch], limit: int = 10
    ) -> list[dict]:
        """Rank comparable markets, including near misses, for diagnostics."""
        comparisons: list[dict] = []
        for match in matches:
            market_type = match.events[0].market_type
            required_keys = (
                ("home", "draw", "away")
                if market_type == "1x2"
                else ("yes", "no")
                if market_type == "prediction"
                else ("home", "away")
            )
            legs = self._best_odds_per_outcome(match, required_keys)
            if len(legs) != len(required_keys):
                continue
            if len({event.platform for _key, _outcome, event in legs}) < 2:
                continue
            implied = sum(
                1.0 / self._effective_odds(outcome, event)[0]
                for _key, outcome, event in legs
            )
            if implied <= 0:
                continue
            margin = (1.0 / implied - 1.0) * 100
            comparisons.append(
                {
                    "match_id": match.match_id,
                    "sport": match.sport.value,
                    "event_name": f"{match.home_team} vs {match.away_team}",
                    "league": match.league,
                    "market_type": market_type,
                    "margin_pct": round(margin, 4),
                    "break_even_gap_pct": round(max(0.0, -margin), 4),
                    "confidence": round(match.confidence, 2),
                    "platform_count": len({event.platform for event in match.events}),
                    "legs": [
                        {
                            "key": key,
                            "outcome": outcome.name,
                            "platform": event.platform.value,
                            "odds": outcome.decimal_odds,
                            "effective_odds": round(
                                self._effective_odds(outcome, event)[0], 6
                            ),
                            "execution_cost_pct": round(
                                self._effective_odds(outcome, event)[1], 4
                            ),
                            "url": outcome.url or event.url,
                        }
                        for key, outcome, event in legs
                    ],
                }
            )
        comparisons.sort(key=lambda item: item["margin_pct"], reverse=True)
        return comparisons[:limit]

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
            start_time=match.start_time,
            country=match.events[0].country,
            competition=match.league,
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
            start_time=match.start_time,
            country=match.events[0].country,
            competition=match.league,
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
            start_time=event.start_time,
            country=event.country,
            competition=event.competition,
        )

    def _calculate_arb(
        self,
        match_id: str,
        sport,
        event_name: str,
        league: str,
        market_type: str,
        legs: list[tuple[str, MarketOutcome, ScrapedEvent]],
        start_time: datetime | None = None,
        country: str = "",
        competition: str = "",
    ) -> ArbitrageOpportunity | None:
        if len(legs) < 2:
            return None

        fee_adjusted_probs: list[float] = []
        warnings: list[str] = []
        min_liquidity: float | None = None

        execution_costs: list[float] = []
        calculation_time = datetime.now(timezone.utc)
        for _key, outcome, event in legs:
            effective_odds, execution_cost_pct = self._effective_odds(outcome, event)
            if effective_odds <= 1:
                return None
            fee_adjusted_probs.append(1.0 / effective_odds)
            execution_costs.append(execution_cost_pct)

            if event.platform == Platform.POLYMARKET and not outcome.ask_levels:
                return None
            if (
                event.platform == Platform.POLYMARKET
                and outcome.quote_fetched_at
                and (calculation_time - outcome.quote_fetched_at).total_seconds()
                > self.quote_ttl_seconds
            ):
                return None

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

        # Solve for a common winning payout using actual CLOB ask depth. The cost
        # function is monotonic, so binary search also scales the opportunity to
        # the largest safely executable bankroll when depth is the limiting leg.
        depth_cap = min(
            (
                sum(level.size for level in outcome.ask_levels)
                * (1 - self.liquidity_buffer_pct / 100)
                for _key, outcome, event in legs
                if event.platform == Platform.POLYMARKET
            ),
            default=self.bankroll * 10,
        )
        low, high = 0.0, max(0.0, min(self.bankroll * 10, depth_cap))
        best_allocations: list[StakeAllocation] | None = None
        for _ in range(60):
            target = (low + high) / 2
            candidate = [
                self._allocation_for_target(key, outcome, event, target, cost_pct)
                for (key, outcome, event), cost_pct in zip(legs, execution_costs)
            ]
            if any(allocation is None for allocation in candidate):
                high = target
                continue
            allocations = [allocation for allocation in candidate if allocation]
            if sum(allocation.stake for allocation in allocations) <= self.bankroll:
                low = target
                best_allocations = allocations
            else:
                high = target

        if not best_allocations:
            return None
        allocations = best_allocations
        total_stake = round(sum(allocation.stake for allocation in allocations), 2)
        guaranteed_return = round(min(allocation.net_payout for allocation in allocations), 2)
        guaranteed_profit = round(guaranteed_return - total_stake, 2)
        profit_pct = guaranteed_profit / total_stake * 100 if total_stake else 0.0
        if profit_pct < self.min_profit_pct:
            return None
        minimum_allowed_payout = total_stake * (1 + self.min_profit_pct / 100)
        for allocation in allocations:
            if allocation.bet_type == "sportsbook":
                effective_factor = (
                    allocation.net_payout / allocation.gross_payout
                    if allocation.gross_payout > 0 else 1.0
                )
                allocation.minimum_decimal_odds = round(
                    minimum_allowed_payout
                    / max(allocation.stake * effective_factor, 0.000001),
                    4,
                )
            elif allocation.shares:
                other_cost = total_stake - allocation.stake
                maximum_leg_cost = (
                    allocation.net_payout / (1 + self.min_profit_pct / 100)
                ) - other_cost
                allocation.maximum_price = round(
                    max(0.0, min(0.99, (maximum_leg_cost - allocation.fee_amount) / allocation.shares)),
                    4,
                )

        if min_liquidity is not None:
            max_stake = min(min_liquidity * (1 - self.liquidity_buffer_pct / 100), total_stake)
            if max_stake < total_stake * 0.1:
                warnings.append(f"Low liquidity: ${min_liquidity:.0f} available")

        if any(a.platform == Platform.POLYMARKET for a in allocations):
            warnings.append("Verify that Polymarket and sportsbook settlement/void rules match")

        now = datetime.now(timezone.utc)
        quote_times = [
            allocation.quote_fetched_at for allocation in allocations if allocation.quote_fetched_at
        ]
        oldest_quote = min(quote_times) if quote_times else now
        age = max(0.0, (now - oldest_quote).total_seconds())
        freshness = "fresh" if age <= self.quote_aging_seconds else "aging"
        expires_at = oldest_quote + timedelta(seconds=self.quote_ttl_seconds)
        fingerprint_source = "|".join(
            [
                sport.value,
                self.normalizer.clean_team_name(event_name),
                start_time.date().isoformat() if start_time else "",
                market_type,
                *sorted(key for key, _outcome, _event in legs),
            ]
        )
        fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()[:24]

        return ArbitrageOpportunity(
            match_id=match_id,
            sport=sport,
            event_name=event_name,
            league=league,
            market_type=market_type,
            profit_pct=profit_pct,
            total_stake=total_stake,
            guaranteed_return=guaranteed_return,
            guaranteed_profit=guaranteed_profit,
            legs=allocations,
            detected_at=datetime.now(timezone.utc),
            min_liquidity_usd=min_liquidity,
            warnings=warnings,
            fingerprint=fingerprint,
            country=country,
            competition=competition or league,
            start_time=start_time,
            last_verified_at=now,
            quote_expires_at=expires_at,
            freshness_status=freshness,
            execution_safe=True,
            requested_bankroll=self.bankroll,
        )

    def _allocation_for_target(
        self,
        outcome_key: str,
        outcome: MarketOutcome,
        event: ScrapedEvent,
        target_payout: float,
        execution_cost_pct: float,
    ) -> StakeAllocation | None:
        if target_payout <= 0:
            return None
        if event.platform != Platform.POLYMARKET:
            effective_odds = self._effective_odds(outcome, event)[0]
            stake = self._round_up_cents(target_payout / effective_odds)
            net_payout = round(stake * effective_odds, 2)
            return StakeAllocation(
                platform=event.platform,
                outcome_name=outcome.name,
                outcome_key=outcome_key,
                decimal_odds=outcome.decimal_odds,
                stake=stake,
                potential_return=net_payout,
                gross_payout=round(stake * outcome.decimal_odds, 2),
                net_payout=net_payout,
                url=outcome.url or event.url,
                fee_pct=execution_cost_pct,
                bet_type="sportsbook",
                quote_fetched_at=outcome.quote_fetched_at,
                source_timestamp=outcome.source_timestamp,
                selection_id=outcome.selection_id,
            )

        shares_needed = math.ceil(target_payout * 100 - 1e-9) / 100
        remaining = shares_needed
        base_cost = 0.0
        fee_amount = 0.0
        depth_used: list[dict[str, float]] = []
        fee_rate = self._safe_fee_rate(outcome)
        buffer_factor = 1 - self.liquidity_buffer_pct / 100
        for level in sorted(outcome.ask_levels, key=lambda item: item.price):
            available = level.size * buffer_factor
            take = min(remaining, available)
            if take <= 0:
                continue
            base_cost += take * level.price
            fee_amount += take * fee_rate * level.price * (1 - level.price)
            depth_used.append({"price": level.price, "shares": round(take, 4)})
            remaining -= take
            if remaining <= 0.000001:
                break
        if remaining > 0.000001:
            return None
        cost_before_rounding = (base_cost + fee_amount) / max(
            1 - self.slippage_pct / 100, 0.000001
        )
        stake = self._round_up_cents(cost_before_rounding)
        minimum_order = self._float(outcome.raw.get("minimum_order_size"))
        if minimum_order and shares_needed < minimum_order:
            return None
        average_price = base_cost / shares_needed
        return StakeAllocation(
            platform=event.platform,
            outcome_name=outcome.name,
            outcome_key=outcome_key,
            decimal_odds=1 / average_price,
            stake=stake,
            potential_return=round(shares_needed, 2),
            gross_payout=round(shares_needed, 2),
            net_payout=round(shares_needed, 2),
            url=outcome.url or event.url,
            fee_pct=execution_cost_pct,
            bet_type="prediction_yes",
            price=outcome.ask_levels[0].price,
            average_price=average_price,
            shares=shares_needed,
            fee_amount=fee_amount,
            quote_fetched_at=outcome.quote_fetched_at,
            source_timestamp=outcome.source_timestamp,
            best_price_size=outcome.ask_levels[0].size,
            depth_used=depth_used,
            available_depth=[
                {"price": level.price, "shares": level.size}
                for level in sorted(outcome.ask_levels, key=lambda item: item.price)
            ],
            token_id=outcome.token_id,
            selection_id=outcome.selection_id,
            maximum_price=depth_used[-1]["price"] if depth_used else None,
            warnings=["Confirm this YES market has the same settlement and void rules as the sportsbook legs"],
        )

    @staticmethod
    def _round_up_cents(value: float) -> float:
        return math.ceil(value * 100 - 1e-9) / 100

    @staticmethod
    def _float(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _safe_fee_rate(self, outcome: MarketOutcome) -> float:
        return max(0.0, self._float(outcome.raw.get("fee_rate")))

    def _effective_odds(
        self, outcome: MarketOutcome, event: ScrapedEvent
    ) -> tuple[float, float]:
        """Return immediately executable odds and their equivalent cost percent."""
        raw_odds = outcome.decimal_odds
        if raw_odds <= 1:
            return raw_odds, 0.0

        effective_odds = raw_odds
        if event.platform == Platform.POLYMARKET:
            price = 1.0 / raw_odds
            try:
                fee_rate = float(outcome.raw.get("fee_rate", 0.0))
            except (TypeError, ValueError):
                fee_rate = 0.0
            # Official taker fee formula per share:
            # fee = fee_rate * price * (1 - price).
            cost_per_share = price + fee_rate * price * (1 - price)
            if cost_per_share > 0:
                effective_odds = 1.0 / cost_per_share
        else:
            platform_fee = self.platform_fees.get(
                event.platform, self.default_fee_pct
            )
            effective_odds *= 1 - platform_fee / 100

        effective_odds *= 1 - self.slippage_pct / 100
        execution_cost_pct = max(0.0, (1 - effective_odds / raw_odds) * 100)
        return effective_odds, execution_cost_pct
