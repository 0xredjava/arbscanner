#!/usr/bin/env python3
"""Sports betting arbitrage scanner — CLI entry point.

Usage:
    python scan.py                  # Run continuous scan loop
    python scan.py --once           # Single scan cycle
    python scan.py --platforms polymarket,cloudbet
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import get_settings
from orchestrator import ArbOrchestrator
from utils.logging import setup_logging

RISK_BANNER = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                         ⚠  RISK WARNING  ⚠                                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  • Sports betting arbitrage may be ILLEGAL in your jurisdiction.            ║
║  • Bookmakers may void bets, limit accounts, or withhold winnings.          ║
║  • Polymarket uses USDC on Polygon — understand settlement & oracle risks.  ║
║  • Auto-execution can lose funds due to odds movement, fees, and slippage.  ║
║  • NEVER share private keys. Use a dedicated wallet with limited funds.       ║
║  • Start in PAPER TRADING mode. Only go live after extensive testing.        ║
║  • This software is for EDUCATIONAL purposes. No warranty of any kind.       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sports Betting Arbitrage Scanner")
    parser.add_argument("--once", action="store_true", help="Run a single scan cycle")
    parser.add_argument(
        "--platforms",
        type=str,
        default=None,
        help="Comma-separated platform list (overrides .env)",
    )
    parser.add_argument(
        "--min-profit",
        type=float,
        default=None,
        help="Minimum profit %% threshold",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=None,
        help="Total bankroll for stake sizing ($)",
    )
    parser.add_argument(
        "--no-risk-banner",
        action="store_true",
        help="Suppress risk warning banner",
    )
    return parser.parse_args()


def apply_cli_overrides(settings, args: argparse.Namespace) -> None:
    if args.platforms:
        enabled = [p.strip().lower() for p in args.platforms.split(",")]
        for attr in [
            "enable_polymarket", "enable_stake", "enable_bcgame",
            "enable_shuffle", "enable_cloudbet", "enable_tgcasino",
            "enable_thunderpick",
        ]:
            platform_name = attr.replace("enable_", "")
            setattr(settings, attr, platform_name in enabled)
    if args.min_profit is not None:
        settings.min_profit_pct = args.min_profit
    if args.bankroll is not None:
        settings.default_bankroll = args.bankroll


async def main() -> None:
    args = parse_args()
    settings = get_settings()
    apply_cli_overrides(settings, args)

    setup_logging(settings.log_level)

    if not args.no_risk_banner:
        print(RISK_BANNER)

    orchestrator = ArbOrchestrator(settings)

    if args.once:
        await orchestrator.run_once()
    else:
        await orchestrator.run_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScanner stopped.")