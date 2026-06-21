"""Supabase REST persistence for scan results."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

import httpx

from config.settings import Settings
from models.odds import ArbitrageOpportunity, NormalizedOdds


class SupabaseStore:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.supabase_url.rstrip("/")
        self.key = settings.supabase_service_role_key

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.key)

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.key,
            "authorization": f"Bearer {self.key}",
            "content-type": "application/json",
        }
        if prefer:
            headers["prefer"] = prefer
        return headers

    def _table_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    async def health(self) -> dict[str, Any]:
        if not self.enabled:
            return {"configured": False, "ok": False}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    self._table_url("scan_runs"),
                    params={"select": "id", "limit": "1"},
                    headers=self._headers(),
                )
                response.raise_for_status()
            return {"configured": True, "ok": True}
        except Exception as exc:
            return {"configured": True, "ok": False, "error": str(exc)}

    async def create_scan_run(self, payload: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                self._table_url("scan_runs"),
                json=payload,
                headers=self._headers("return=representation"),
            )
            response.raise_for_status()
            rows = response.json()
        return rows[0]["id"] if rows else None

    async def save_platform_statuses(self, statuses: list[dict[str, Any]]) -> None:
        if not self.enabled or not statuses:
            return
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self._table_url('platform_status')}?on_conflict=platform",
                json=statuses,
                headers=self._headers("resolution=merge-duplicates"),
            )
            response.raise_for_status()

    async def save_events(self, scan_id: str | None, events: list[NormalizedOdds]) -> None:
        if not self.enabled or not scan_id or not events:
            return
        payload = [self._event_payload(scan_id, event) for event in events]
        await self._bulk_insert("events", payload)

    async def save_opportunities(
        self,
        scan_id: str | None,
        opportunities: list[ArbitrageOpportunity],
    ) -> None:
        if not self.enabled or not scan_id or not opportunities:
            return
        payload = [self._opportunity_payload(scan_id, opportunity) for opportunity in opportunities]
        await self._bulk_insert("opportunities", payload)

    async def latest_scan(self) -> dict[str, Any] | None:
        rows = await self._select(
            "scan_runs",
            {"select": "*", "order": "started_at.desc", "limit": "1"},
        )
        return rows[0] if rows else None

    async def latest_platforms(self) -> list[dict[str, Any]]:
        return await self._select(
            "platform_status",
            {"select": "*", "order": "platform.asc"},
        )

    async def latest_opportunities(self) -> list[dict[str, Any]]:
        latest = await self.latest_scan()
        if not latest:
            return []
        return await self._select(
            "opportunities",
            {
                "select": "*",
                "scan_id": f"eq.{latest['id']}",
                "order": "profit_pct.desc",
            },
        )

    async def latest_events(self) -> list[dict[str, Any]]:
        latest = await self.latest_scan()
        if not latest:
            return []
        return await self._select_all(
            "events",
            {
                "select": "platform,sport,event_key,event_id,home_team,away_team,league,start_time,market_type,outcome_name,decimal_odds,implied_prob,fee_adjusted_prob,liquidity_usd,url",
                "scan_id": f"eq.{latest['id']}",
                "order": "platform.asc,sport.asc,start_time.asc,event_id.asc",
            },
        )

    async def _bulk_insert(self, table: str, payload: list[dict[str, Any]]) -> None:
        if not payload:
            return
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self._table_url(table),
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()

    async def _select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                self._table_url(table),
                params=params,
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def _select_all(
        self, table: str, params: dict[str, str], page_size: int = 1000
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        rows: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for start in range(0, 100_000, page_size):
                headers = self._headers()
                headers["range"] = f"{start}-{start + page_size - 1}"
                response = await client.get(
                    self._table_url(table), params=params, headers=headers
                )
                response.raise_for_status()
                page = response.json()
                rows.extend(page)
                if len(page) < page_size:
                    break
        return rows

    def _event_payload(self, scan_id: str, event: NormalizedOdds) -> dict[str, Any]:
        return {
            "scan_id": scan_id,
            "platform": event.platform.value,
            "sport": event.sport.value,
            "event_key": event.event_key,
            "event_id": event.event_id,
            "home_team": event.home_team,
            "away_team": event.away_team,
            "league": event.league,
            "start_time": _iso(event.start_time),
            "market_type": event.market_type,
            "outcome_name": event.outcome_name,
            "decimal_odds": event.decimal_odds,
            "implied_prob": event.implied_prob,
            "fee_adjusted_prob": event.fee_adjusted_prob,
            "liquidity_usd": event.liquidity_usd,
            "url": event.url,
        }

    def _opportunity_payload(
        self,
        scan_id: str,
        opportunity: ArbitrageOpportunity,
    ) -> dict[str, Any]:
        data = opportunity.to_dict()
        return {
            "scan_id": scan_id,
            "match_id": opportunity.match_id,
            "sport": opportunity.sport.value,
            "event_name": opportunity.event_name,
            "league": opportunity.league,
            "market_type": opportunity.market_type,
            "profit_pct": opportunity.profit_pct,
            "total_stake": opportunity.total_stake,
            "guaranteed_return": opportunity.guaranteed_return,
            "guaranteed_profit": opportunity.guaranteed_profit,
            "total_implied_prob": round(
                sum(1 / leg.decimal_odds for leg in opportunity.legs if leg.decimal_odds > 0),
                8,
            ),
            "legs": data["legs"],
            "warnings": opportunity.warnings,
            "detected_at": _iso(opportunity.detected_at),
        }


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
