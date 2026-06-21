"""Main scan loop — coordinates scrapers, matching, and notifications."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from calculator.arb_calculator import ArbCalculator
from config.settings import Settings
from matcher.event_matcher import EventMatcher
from models.odds import ArbitrageOpportunity, NormalizedOdds, ScrapedEvent, Sport
from normalizer.odds_normalizer import OddsNormalizer
from notifier.console import ConsoleNotifier
from scrapers.registry import build_scrapers

logger = logging.getLogger("arb_scanner.orchestrator")


class ArbOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.scrapers = build_scrapers(settings)
        self.normalizer = OddsNormalizer(
            default_fee_pct=settings.default_platform_fee_pct,
            slippage_pct=settings.slippage_pct,
        )
        self.matcher = EventMatcher(
            threshold=settings.fuzzy_match_threshold,
            max_time_diff_minutes=settings.max_event_time_diff_minutes,
        )
        self.calculator = ArbCalculator(
            min_profit_pct=settings.min_profit_pct,
            bankroll=settings.default_bankroll,
            default_fee_pct=settings.default_platform_fee_pct,
            slippage_pct=settings.slippage_pct,
            liquidity_buffer_pct=settings.liquidity_buffer_pct,
        )
        self.console = ConsoleNotifier()
        self._latest_opportunities: list[ArbitrageOpportunity] = []
        self._latest_events: list[ScrapedEvent] = []
        self._latest_normalized: list[NormalizedOdds] = []
        self._latest_platform_statuses: list[dict] = []

    @property
    def latest_opportunities(self) -> list[ArbitrageOpportunity]:
        return self._latest_opportunities

    @property
    def latest_events(self) -> list[ScrapedEvent]:
        return self._latest_events

    @property
    def latest_normalized(self) -> list[NormalizedOdds]:
        return self._latest_normalized

    @property
    def latest_platform_statuses(self) -> list[dict]:
        return self._latest_platform_statuses

    async def run_once(self) -> list[ArbitrageOpportunity]:
        logger.info("Starting scan cycle across %d platforms", len(self.scrapers))

        # Fetch from all platforms concurrently, preserving per-platform health.
        tasks = [self._fetch_platform(scraper) for scraper in self.scrapers]
        results = await asyncio.gather(*tasks)
        all_events: list[ScrapedEvent] = []
        platform_statuses: list[dict] = []
        for platform_events, status in results:
            all_events.extend(platform_events)
            platform_statuses.append(status)

        all_events = self._filter_moneyline_events(all_events)
        self._latest_events = all_events
        self._latest_platform_statuses = platform_statuses
        logger.info("Total events fetched: %d", len(all_events))

        # Normalize
        normalized = self.normalizer.normalize_all(all_events)
        self._latest_normalized = normalized
        logger.debug("Normalized %d outcome records", len(normalized))

        # Match cross-platform events
        matches = self.matcher.match_events(all_events)

        # Detect cross-platform arbs
        cross_arbs = self.calculator.find_arbitrages(matches)

        # Deduplicate by match_id
        seen: set[str] = set()
        opportunities: list[ArbitrageOpportunity] = []
        for arb in cross_arbs:
            if arb.match_id not in seen:
                seen.add(arb.match_id)
                opportunities.append(arb)

        opportunities.sort(key=lambda a: a.profit_pct, reverse=True)
        self._latest_opportunities = opportunities

        # Output
        self.console.notify(opportunities)
        self._write_json_log(opportunities)

        return opportunities

    async def _fetch_platform(self, scraper) -> tuple[list[ScrapedEvent], dict]:
        started = datetime.now(timezone.utc)
        status = {
            "platform": scraper.platform.value,
            "status": "ok",
            "fetch_method": getattr(scraper, "fetch_method", "api"),
            "event_count": 0,
            "last_success_at": None,
            "last_error": None,
        }
        try:
            events = await scraper.fetch_events()
            status["event_count"] = len(events)
            status["last_success_at"] = datetime.now(timezone.utc).isoformat()
            logger.info("Fetched %d events from %s", len(events), scraper.platform.value)
            return events, status
        except Exception as exc:
            status["status"] = "failed"
            status["last_error"] = str(exc)
            logger.exception("Failed to fetch from %s", scraper.platform.value)
            return [], status
        finally:
            status["duration_ms"] = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

    def _filter_moneyline_events(self, events: list[ScrapedEvent]) -> list[ScrapedEvent]:
        filtered: list[ScrapedEvent] = []
        for event in events:
            if event.is_live:
                continue
            if event.market_type not in ("moneyline", "1x2", "prediction"):
                continue
            outcome_count = len(event.outcomes)
            if outcome_count == 2:
                filtered.append(event)
            elif outcome_count == 3 and (event.sport == Sport.SOCCER or event.market_type == "1x2"):
                filtered.append(event)
        return filtered

    async def run_loop(self) -> None:
        logger.info(
            "Arb scanner running. Refresh: %ds, min profit: %.1f%%",
            self.settings.refresh_interval_seconds,
            self.settings.min_profit_pct,
        )
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Scan cycle failed")
            await asyncio.sleep(self.settings.refresh_interval_seconds)

    def _write_json_log(self, opportunities: list[ArbitrageOpportunity]) -> None:
        self.settings.json_log_path.parent.mkdir(parents=True, exist_ok=True)
        events_by_platform: dict[str, int] = {}
        for event in self._latest_events:
            key = event.platform.value
            events_by_platform[key] = events_by_platform.get(key, 0) + 1

        payload = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "platforms": self.settings.enabled_platforms,
            "event_count": len(self._latest_events),
            "events_by_platform": events_by_platform,
            "platform_statuses": self._latest_platform_statuses,
            "opportunity_count": len(opportunities),
            "opportunities": [arb.to_dict() for arb in opportunities],
        }
        with open(self.settings.json_log_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info("Wrote JSON log to %s", self.settings.json_log_path)
