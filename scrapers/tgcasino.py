"""TG.Casino public sportsbook-provider API adapter."""

from models.odds import Platform
from scrapers.spt_feed import SptFeedScraper


class TGCasinoScraper(SptFeedScraper):
    platform = Platform.TGCASINO
    fee_pct = 2.0
    public_url = "https://www.tg.casino/sports/event"

    def __init__(self, settings, http, proxy_rotator) -> None:
        super().__init__(settings, http, proxy_rotator)
        self.feed_url = settings.tgcasino_feed_url
        self.brand_id = settings.tgcasino_brand_id
