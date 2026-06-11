# Sports Betting Arbitrage Scanner

A modular, async Python scanner that detects arbitrage opportunities across **Polymarket**, **Stake**, **BC.Game**, **Shuffle**, **Cloudbet**, **TG.Casino**, and **Thunderpick**.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         scan.py / dashboard.py                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                      orchestrator.py                            │
│  (scan loop: fetch → normalize → match → calculate → notify)    │
└──┬────────┬──────────┬──────────┬──────────┬──────────┬────────┘
   │        │          │          │          │          │
   ▼        ▼          ▼          ▼          ▼          ▼
scrapers  normalizer  matcher   calculator  notifier   executor
   │                                              │         │
   ├─ polymarket (Gamma + CLOB APIs)             ├─ console  ├─ paper_trader
   ├─ cloudbet (public REST API)                 └─ telegram └─ live_executor
   ├─ stake / bcgame / shuffle (Playwright)
   ├─ tgcasino / thunderpick (Playwright)
   └─ the_odds_api (optional aggregator)
```

### Data Flow

1. **Scrapers** fetch raw events/odds per platform (async, concurrent)
2. **Normalizer** converts to decimal/American/implied-prob with fee adjustment
3. **Event Matcher** fuzzy-matches same fixtures across platforms (team names, time, league)
4. **Arb Calculator** detects guaranteed-profit opportunities and sizes stakes
5. **Notifiers** output console table + JSON log + Telegram alerts
6. **Executor** logs paper trades or (optionally) places live orders

## Quick Start

### 1. Prerequisites

- Python 3.11+
- (Optional) Playwright browsers for web scraping platforms

### 2. Install

```bash
cd arb-scanner
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt

# Only if using Playwright scrapers (Stake, BC.Game, etc.)
playwright install chromium
```

### 3. Configure

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # macOS/Linux
```

Edit `.env` — at minimum, set your watched sports and min profit threshold. For Telegram alerts, set `TELEGRAM_ENABLED=true` and your bot token/chat ID.

### 4. Run

**Single scan (recommended first run):**
```bash
python scan.py --once --platforms polymarket,cloudbet
```

**Continuous polling:**
```bash
python scan.py
```

**Polymarket only:**
```bash
python scan.py --once --platforms polymarket --min-profit 1.5
```

**Streamlit dashboard:**
```bash
streamlit run dashboard.py
```

## Polymarket Integration

Polymarket is the primary integration and uses **public APIs** (no auth for reading):

| API | Base URL | Purpose |
|-----|----------|---------|
| Gamma | `https://gamma-api.polymarket.com` | Events, markets, sports tags |
| CLOB | `https://clob.polymarket.com` | Live prices, orderbooks |
| Data | `https://data-api.polymarket.com` | Positions, trades, OI |

### Example: Fetch sports markets

```python
import httpx

# Get active sports-tagged events
resp = httpx.get(
    "https://gamma-api.polymarket.com/events",
    params={"tag_id": 100381, "active": "true", "closed": "false", "limit": 10},
)
events = resp.json()

for event in events:
    for market in event.get("markets", []):
        print(event["title"], market.get("outcomePrices"))
```

### Example: Live trading with py-clob-client

```python
from py_clob_client.client import ClobClient
from py_clob_client.order_builder.constants import BUY

client = ClobClient(
    host="https://clob.polymarket.com",
    key="YOUR_PRIVATE_KEY",
    chain_id=137,  # Polygon
)
creds = client.create_or_derive_api_creds()
client.set_api_creds(creds)

order = client.create_order(
    token_id="TOKEN_ID_FROM_GAMMA",
    price=0.45,
    size=10.0,
    side=BUY,
)
client.post_order(order)
```

See `scrapers/polymarket.py` for the full integration and `create_polymarket_client()` helper.

## Output

- **Console**: Rich table with profit %, stakes, platform links
- **JSON**: `data/arbs.json` — latest scan snapshot
- **History**: `data/arb_history.jsonl` — paper trade log (one JSON object per line)
- **Telegram**: Top 5 opportunities per cycle (if enabled)

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MIN_PROFIT_PCT` | 2.0 | Minimum arb profit after fees |
| `DEFAULT_BANKROLL` | 1000 | Total stake for sizing |
| `REFRESH_INTERVAL_SECONDS` | 30 | Polling interval |
| `PAPER_TRADING` | true | Log simulated bets |
| `SLIPPAGE_PCT` | 1.0 | Assumed slippage haircut |
| `FUZZY_MATCH_THRESHOLD` | 75 | Event matching confidence (0-100) |
| `PROXY_LIST` | — | Comma-separated proxy URLs |

## Extending

### Add a new bookmaker

1. Create `scrapers/newbook.py` extending `BaseScraper` or `PlaywrightScraper`
2. Register in `scrapers/registry.py` → `SCRAPER_MAP`
3. Add `ENABLE_NEWBOOK=true` to `.env.example` and `config/settings.py`
4. Set platform fee in `normalizer/odds_normalizer.py` → `PLATFORM_FEES`

### Add auto-betting for a bookmaker

1. Implement bet placement in `executor/live_executor.py`
2. Options: official API, Playwright automation, or browser extension
3. Set `EXECUTION_MODE=live` and `AUTO_EXECUTE=true` (after thorough testing)

### Crypto deposits/withdrawals (conceptual)

| Platform | Typical deposit | Chain |
|----------|----------------|-------|
| Polymarket | USDC | Polygon |
| Stake | BTC, ETH, USDT, etc. | Multi-chain |
| BC.Game | Crypto (100+ coins) | Multi-chain |
| Cloudbet | BTC, ETH, USDT | Multi-chain |

**Best practice**: Use separate wallets per platform. Bridge USDT via official bridges only. Never store large balances on betting platforms.

## Risk Warnings & Best Practices

### Legal
- Sports betting laws vary by country/state. Verify legality before betting.
- Prediction markets (Polymarket) may be restricted in your jurisdiction.
- Arbitrage is not illegal per se, but bookmakers may ban winning accounts.

### Financial
- **Start with paper trading** (`PAPER_TRADING=true`).
- Real arbs are rare, short-lived, and often smaller than displayed after fees.
- Account for: platform fees (1-5%), withdrawal fees, FX spread, slippage.
- Polymarket liquidity can be thin — your order may not fill at displayed price.

### Account Safety
- Use unique accounts; don't arb between your own accounts on the same platform.
- Rotate proxies for geo-restricted sites; respect rate limits.
- Never share private keys or store them in plaintext outside `.env`.
- Use a dedicated wallet with limited funds for Polymarket trading.

### Bankroll Management
- Never risk more than 1-2% of total bankroll per arb.
- Keep funds distributed across platforms for fast execution.
- Track actual vs expected profit — variance and voided bets happen.

## Project Structure

```
arb-scanner/
├── scan.py                 # CLI entry point
├── dashboard.py            # Streamlit UI
├── orchestrator.py         # Scan loop coordinator
├── config/settings.py      # Pydantic settings from .env
├── models/odds.py          # Data models
├── scrapers/               # Per-platform fetchers
│   ├── polymarket.py       # Gamma + CLOB (primary)
│   ├── cloudbet.py         # Public REST API
│   ├── playwright_base.py  # Headless browser base
│   └── stake.py / bcgame.py / ...
├── normalizer/             # Odds format conversion
├── matcher/                # Fuzzy event matching
├── calculator/             # Arb detection + stake sizing
├── notifier/               # Console + Telegram
├── executor/               # Paper + live trading
├── utils/                  # HTTP, proxy, logging
├── data/                   # JSON output
└── logs/                   # Application logs
```

## License

Educational use only. No warranty. Use at your own risk.