"""Base scraper interface for all platforms."""

from __future__ import annotations

import abc
import logging
from typing import TYPE_CHECKING

from models.odds import Platform, ScrapedEvent

if TYPE_CHECKING:
    from config.settings import Settings
    from utils.http import AsyncHttpClient
    from utils.proxy import ProxyRotator

logger = logging.getLogger("arb_scanner.scrapers")


class BaseScraper(abc.ABC):
    platform: Platform
    fee_pct: float = 2.0
    fetch_method: str = "api"

    def __init__(
        self,
        settings: Settings,
        http: AsyncHttpClient,
        proxy_rotator: ProxyRotator,
    ) -> None:
        self.settings = settings
        self.http = http
        self.proxy_rotator = proxy_rotator
        self.logger = logging.getLogger(f"arb_scanner.scrapers.{self.platform.value}")

    @abc.abstractmethod
    async def fetch_events(self) -> list[ScrapedEvent]:
        """Fetch all relevant events/odds from the platform."""

    async def safe_fetch(self) -> list[ScrapedEvent]:
        try:
            events = await self.fetch_events()
            self.logger.info("Fetched %d events from %s", len(events), self.platform.value)
            return events
        except Exception:
            self.logger.exception("Failed to fetch from %s", self.platform.value)
            return []
