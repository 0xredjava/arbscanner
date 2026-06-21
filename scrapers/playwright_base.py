"""Playwright-based scraper base for sites without public APIs."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from models.odds import MarketOutcome, Platform, ScrapedEvent, Sport
from scrapers.base import BaseScraper

logger = logging.getLogger("arb_scanner.scrapers.playwright")


class PlaywrightScraper(BaseScraper):
    """Headless browser scraper with proxy support and API interception fallback."""

    base_url: str = ""
    api_patterns: list[str] = []  # URL substrings to intercept
    fetch_method = "playwright"

    async def fetch_events(self) -> list[ScrapedEvent]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.error(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
            return await self._fallback_fetch()

        captured: list[dict[str, Any]] = []

        async with async_playwright() as pw:
            launch_args: dict[str, Any] = {"headless": self.settings.use_playwright_headless}
            proxy = self.proxy_rotator.playwright_proxy()
            if proxy:
                launch_args["proxy"] = proxy

            browser = await pw.chromium.launch(**launch_args)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            async def on_response(response: Any) -> None:
                url = response.url
                if any(pat in url for pat in self.api_patterns):
                    try:
                        if "json" in (response.headers.get("content-type") or ""):
                            body = await response.json()
                            captured.append({"url": url, "data": body})
                    except Exception:
                        pass

            page.on("response", on_response)

            try:
                await page.goto(
                    self.base_url,
                    wait_until="networkidle",
                    timeout=self.settings.playwright_timeout_ms,
                )
                await asyncio.sleep(3)
            except Exception as exc:
                self.logger.warning("Navigation issue for %s: %s", self.platform.value, exc)
            finally:
                await browser.close()

        if captured:
            return self._parse_intercepted(captured)
        return await self._fallback_fetch()

    def _parse_intercepted(self, captured: list[dict[str, Any]]) -> list[ScrapedEvent]:
        """Override in subclass to parse intercepted API responses."""
        return []

    async def _fallback_fetch(self) -> list[ScrapedEvent]:
        """Override in subclass. Return empty or use alternate HTTP endpoint."""
        self.logger.info("Using fallback for %s (no intercepted data)", self.platform.value)
        return []


def parse_generic_odds_json(
    data: Any,
    platform: Platform,
    sport: Sport = Sport.OTHER,
) -> list[ScrapedEvent]:
    """Best-effort parser for common sportsbook JSON shapes."""
    events: list[ScrapedEvent] = []
    items = data if isinstance(data, list) else data.get("events") or data.get("data") or []

    for item in items:
        home = item.get("homeTeam") or item.get("home") or item.get("team1", "")
        away = item.get("awayTeam") or item.get("away") or item.get("team2", "")
        if isinstance(home, dict):
            home = home.get("name", "")
        if isinstance(away, dict):
            away = away.get("name", "")

        outcomes: list[MarketOutcome] = []
        for sel in item.get("selections") or item.get("outcomes") or item.get("markets", [{}])[0].get("selections", []):
            odds = sel.get("odds") or sel.get("price") or sel.get("decimal")
            if odds and float(odds) > 1:
                outcomes.append(MarketOutcome(name=sel.get("name", ""), decimal_odds=float(odds)))

        if len(outcomes) >= 2:
            events.append(
                ScrapedEvent(
                    platform=platform,
                    sport=sport,
                    event_id=str(item.get("id", "")),
                    home_team=str(home),
                    away_team=str(away),
                    league=item.get("league", "") or item.get("competition", ""),
                    start_time=None,
                    market_type="moneyline",
                    outcomes=outcomes,
                )
            )
    return events
