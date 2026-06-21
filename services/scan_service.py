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
    ) -> list[dict[str, Any]]:
        stored = await self.store.latest_opportunities()
        if not stored and self._latest_snapshot:
            stored = self._latest_snapshot.get("opportunities", [])

        results = []
        for item in stored:
            legs = item.get("legs") or []
            if sport and item.get("sport") != sport:
                continue
            if min_profit is not None and float(item.get("profit_pct") or 0) < min_profit:
                continue
            if platform and not any(leg.get("platform") == platform for leg in legs):
                continue
            results.append(item)
        return results

    async def _background_loop(self) -> None:
        while True:
            try:
                await self.run_scan(trigger="background")
            except Exception:
                logger.exception("Background scan failed")
            await asyncio.sleep(self.settings.refresh_interval_seconds)
