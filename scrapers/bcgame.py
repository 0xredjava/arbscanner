"""BC.Game public sportsbook-provider API adapter."""

from models.odds import Platform
from scrapers.spt_feed import SptFeedScraper


class BCGameScraper(SptFeedScraper):
    platform = Platform.BCGAME
    fee_pct = 1.0
    public_url = "https://bc.game/sports/event"

    def __init__(self, settings, http, proxy_rotator) -> None:
        super().__init__(settings, http, proxy_rotator)
        self.feed_url = settings.bcgame_feed_url
        self.brand_id = settings.bcgame_brand_id
