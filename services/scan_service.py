"""Lockable scan service shared by API, background loop, and CLI."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from config.settings import Settings
from orchestrator import ArbOrchestrator
from storage.supabase import SupabaseStore

logger = logging.getLogger("arb_scanner.service")


class ScanService:
    def __init__(self, settings: Settings, store: SupabaseStore) -> None:
        self.settings = settings
        self.store = store
        self.orchestrator = ArbOrchestrator(settings)
        self._lock = asyncio.Lock()
        self._background_task: asyncio.Task[None] | None = None
        self._latest_snapshot: dict[str, Any] | None = None

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    def start_background(self) -> None:
        if self._background_task and not self._background_task.done():
            return
        self._background_task = asyncio.create_task(self._background_loop())

    async def stop_background(self) -> None:
        if not self._background_task:
            return
        self._background_task.cancel()
        try:
            await self._background_task
        except asyncio.CancelledError:
            pass

    async def run_scan(self, trigger: str = "manual") -> dict[str, Any]:
        if self._lock.locked():
            return {
                "status": "already_running",
                "running": True,
                "latest": self._latest_snapshot,
            }

        async with self._lock:
            started = datetime.now(timezone.utc)
            status = "success"
            error = None
            opportunities = []
            try:
                opportunities = await self.orchestrator.run_once()
            except Exception as exc:
                logger.exception("Scan failed")
                status = "failed"
                error = str(exc)

            finished = datetime.now(timezone.utc)
            duration_ms = int((finished - started).total_seconds() * 1000)
            events = self.orchestrator.latest_events
            normalized = self.orchestrator.latest_normalized
            platform_statuses = self.orchestrator.latest_platform_statuses

            counts = {
                "event_count": len(events),
                "normalized_event_count": len(normalized),
                "opportunity_count": len(opportunities),
                "platform_count": len(self.settings.enabled_platforms),
            }
            scan_payload = {
                "started_at": started.isoformat(),
                "finished_at": finished.isoformat(),
                "duration_ms": duration_ms,
                "status": status,
                "trigger": trigger,
                "error": error,
                **counts,
            }

            scan_id = await self.store.create_scan_run(scan_payload)
            previous_statuses = await self.store.latest_platforms()
            previous_success = {
                item.get("platform"): item.get("last_success_at")
                for item in previous_statuses
                if item.get("platform") and item.get("last_success_at")
            }
            statuses = [
                {
                    **platform,
                    "last_success_at": platform.get("last_success_at")
                    or previous_success.get(platform["platform"]),
                    "scan_id": scan_id,
                    "enabled": platform["platform"] in self.settings.enabled_platforms,
                    "updated_at": finished.isoformat(),
                }
                for platform in platform_statuses
            ]
            await self.store.save_platform_statuses(statuses)
            await self.store.save_events(scan_id, normalized)
            await self.store.save_opportunities(scan_id, opportunities)

            snapshot = {
                "id": scan_id,
                **scan_payload,
                "running": False,
                "platforms": statuses,
                "opportunities": [opportunity.to_dict() for opportunity in opportunities],
                "comparisons": self.orchestrator.latest_comparisons,
            }
            self._latest_snapshot = snapshot
            return snapshot

    async def latest_scan(self) -> dict[str, Any] | None:
        stored = await self.store.latest_scan()
        return stored or self._latest_snapshot

    async def latest_platforms(self) -> list[dict[str, Any]]:
        stored = await self.store.latest_platforms()
        if stored:
            return stored
        if self._latest_snapshot:
            return self._latest_snapshot.get("platforms", [])
        return [
            {
                "platform": platform,
                "enabled": True,
                "status": "pending",
                "fetch_method": "unknown",
                "source_type": "unknown",
                "event_count": 0,
                "response_count": 0,
                "last_success_at": None,
                "data_timestamp": None,
                "last_error": None,
            }
            for platform in self.settings.enabled_platforms
        ]

    async def latest_opportunities(
        self,
        sport: str | None = None,
        platform: str | None = None,
        min_profit: float | None = None,
        country: str | None = None,
        competition: str | None = None,
    ) -> list[dict[str, Any]]:
        stored = await self.store.latest_opportunities()
        if not stored and self._latest_snapshot:
            stored = self._latest_snapshot.get("opportunities", [])

        fingerprints = [str(item.get("fingerprint") or "") for item in stored]
        lifecycle = await self.store.opportunity_lifecycle_map(
            [fingerprint for fingerprint in fingerprints if fingerprint]
        )
        results = []
        now = datetime.now(timezone.utc)
        for item in stored:
            item = dict(item)
            history = lifecycle.get(str(item.get("fingerprint") or ""), {})
            item["first_found_at"] = history.get("first_found_at") or item.get("detected_at")
            item["last_seen_at"] = history.get("last_seen_at") or item.get("detected_at")
            expires = _parse_datetime(item.get("quote_expires_at"))
            if expires and expires <= now:
                item["freshness_status"] = "expired"
                item["execution_safe"] = False
            legs = item.get("legs") or []
            if sport and item.get("sport") != sport:
                continue
            if min_profit is not None and float(item.get("profit_pct") or 0) < min_profit:
                continue
            if platform and not any(leg.get("platform") == platform for leg in legs):
                continue
            if country and item.get("country") != country:
                continue
            if competition and item.get("competition") != competition:
                continue
            results.append(item)
        return results

    async def opportunity_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return await self.store.opportunity_history(limit=limit)

    async def opportunity_observations(
        self, fingerprint: str, limit: int = 500
    ) -> list[dict[str, Any]]:
        return await self.store.opportunity_observations(fingerprint, limit=limit)

    async def coverage(self) -> dict[str, Any]:
        rows = await self.store.latest_events()
        events = group_event_rows(rows)
        if not events:
            events = [
                {
                    "sport": event.sport.value,
                    "country": event.country,
                    "competition": event.competition or event.league,
                    "platform": event.platform.value,
                }
                for event in self.orchestrator.latest_events
            ]
        return {
            "scope_label": "Worldwide where enabled sources provide markets",
            "sports": sorted({str(event.get("sport") or "") for event in events if event.get("sport")}),
            "countries": sorted({str(event.get("country") or "International / unknown") for event in events}),
            "competitions": sorted({str(event.get("competition") or event.get("league") or "Unknown") for event in events}),
            "platforms": sorted({str(event.get("platform") or "") for event in events if event.get("platform")}),
            "event_count": len(events),
        }

    async def latest_comparisons(self, limit: int = 10) -> list[dict[str, Any]]:
        comparisons = self.orchestrator.latest_comparisons
        if not comparisons and self._latest_snapshot:
            comparisons = self._latest_snapshot.get("comparisons", [])
        return comparisons[:limit]

    async def latest_events(
        self,
        platform: str | None = None,
        sport: str | None = None,
        search: str | None = None,
        limit: int = 2500,
    ) -> list[dict[str, Any]]:
        rows = await self.store.latest_events()
        events = group_event_rows(rows)
        needle = (search or "").strip().casefold()
        filtered = []
        for event in events:
            if platform and event["platform"] != platform:
                continue
            if sport and event["sport"] != sport:
                continue
            if needle:
                haystack = " ".join(
                    str(event.get(key) or "")
                    for key in ("home_team", "away_team", "league", "event_id")
                ).casefold()
                if needle not in haystack:
                    continue
            filtered.append(event)
        return filtered[:limit]

    async def _background_loop(self) -> None:
        while True:
            cycle_started = asyncio.get_running_loop().time()
            try:
                await self.run_scan(trigger="background")
            except Exception:
                logger.exception("Background scan failed")
            elapsed = asyncio.get_running_loop().time() - cycle_started
            await asyncio.sleep(
                max(0.0, self.settings.refresh_interval_seconds - elapsed)
            )


def group_event_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group persisted one-row-per-outcome records into inspectable events."""
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        platform = str(row.get("platform") or "")
        event_id = str(row.get("event_id") or "")
        event_key = str(row.get("event_key") or "")
        if not platform or not event_id:
            continue
        key = (platform, event_id, event_key)
        event = grouped.setdefault(
            key,
            {
                "platform": platform,
                "sport": row.get("sport"),
                "event_key": event_key,
                "event_id": event_id,
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "league": row.get("league"),
                "country": row.get("country") or "International / unknown",
                "competition": row.get("competition") or row.get("league"),
                "start_time": row.get("start_time"),
                "market_type": row.get("market_type"),
                "url": row.get("url"),
                "outcomes": [],
            },
        )
        event["outcomes"].append(
            {
                "name": row.get("outcome_name"),
                "decimal_odds": row.get("decimal_odds"),
                "implied_prob": row.get("implied_prob"),
                "fee_adjusted_prob": row.get("fee_adjusted_prob"),
                "liquidity_usd": row.get("liquidity_usd"),
                "quote_fetched_at": row.get("quote_fetched_at"),
                "source_timestamp": row.get("source_timestamp"),
                "url": row.get("url"),
            }
        )
    return sorted(
        grouped.values(),
        key=lambda event: (
            event["platform"],
            event.get("sport") or "",
            event.get("start_time") or "",
            event.get("home_team") or "",
        ),
    )


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
