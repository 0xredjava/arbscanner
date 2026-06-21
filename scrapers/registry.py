"""Scraper factory — builds enabled scrapers from config."""

from __future__ import annotations

from config.settings import Settings
from scrapers.base import BaseScraper
from scrapers.bcgame import BCGameScraper
from scrapers.cloudbet import CloudbetScraper
from scrapers.polymarket import PolymarketScraper
from scrapers.shuffle import ShuffleScraper
from scrapers.stake import StakeScraper
from scrapers.the_odds_api import TheOddsApiScraper
from scrapers.thunderpick import ThunderpickScraper
from scrapers.tgcasino import TGCasinoScraper
from utils.http import AsyncHttpClient
from utils.proxy import ProxyRotator

SCRAPER_MAP: dict[str, type[BaseScraper]] = {
    "polymarket": PolymarketScraper,
    "stake": StakeScraper,
    "bcgame": BCGameScraper,
    "shuffle": ShuffleScraper,
    "cloudbet": CloudbetScraper,
    "tgcasino": TGCasinoScraper,
    "thunderpick": ThunderpickScraper,
}


def build_scrapers(settings: Settings) -> list[BaseScraper]:
    proxy_rotator = ProxyRotator([])
    http = AsyncHttpClient(proxy_rotator=proxy_rotator)
    scrapers: list[BaseScraper] = []

    for name in settings.enabled_platforms:
        cls = SCRAPER_MAP.get(name)
        if cls:
            scrapers.append(cls(settings, http, proxy_rotator))

    if settings.the_odds_api_key:
        scrapers.append(TheOddsApiScraper(settings, http, proxy_rotator))

    return scrapers
