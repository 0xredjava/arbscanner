"""Stake source status.

Stake's documented public API requires a logged-in session and does not expose
sportsbook odds. The public sportsbook is challenge-blocked in the deployment
region, so the collector reports an honest unavailable state.
"""

from __future__ import annotations

from models.odds import Platform, ScrapedEvent
from scrapers.base import BaseScraper, SourceStatusError


class StakeScraper(BaseScraper):
    platform = Platform.STAKE
    fee_pct = 0.0
    source_type = "unavailable"
    fetch_method = "unavailable"

    async def fetch_events(self) -> list[ScrapedEvent]:
        raise SourceStatusError(
            "unavailable",
            "No supported public Stake sportsbook source; the public page is challenge-blocked",
        )
