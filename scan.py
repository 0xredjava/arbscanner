#!/usr/bin/env python3
"""Local CLI entrypoint for running scanner cycles against public data sources."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import get_settings
from orchestrator import ArbOrchestrator
from utils.logging import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pre-match moneyline arbitrage scanner")
    parser.add_argument("--once", action="store_true", help="Run a single scan cycle")
    parser.add_argument("--platforms", type=str, default=None, help="Comma-separated platform list")
    parser.add_argument("--min-profit", type=float, default=None, help="Minimum profit percent")
    parser.add_argument("--bankroll", type=float, default=None, help="Stake sizing bankroll")
    return parser.parse_args()


def apply_cli_overrides(settings, args: argparse.Namespace) -> None:
    if args.platforms:
        enabled = [p.strip().lower() for p in args.platforms.split(",")]
        for attr in [
            "enable_polymarket",
            "enable_stake",
            "enable_bcgame",
            "enable_shuffle",
            "enable_cloudbet",
            "enable_tgcasino",
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
