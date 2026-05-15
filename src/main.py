"""Polling loop: scrape → normalize → detect arbs → alert. Repeat."""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Type

import yaml

from .alerts import print_arb, print_cycle_summary, print_error, print_info, print_warning
from .arbitrage import find_arbs
from .models import Game
from .normalizer import normalize_games
from .scrapers.base import Scraper
from .scrapers.demo import DemoScraperA, DemoScraperB
from .scrapers.draftkings import DraftKingsScraper
from .scrapers.fanduel import FanDuelScraper
from .state import AlertedState


SCRAPER_REGISTRY: dict[str, Type[Scraper]] = {
    "draftkings": DraftKingsScraper,
    "fanduel": FanDuelScraper,
    "demo_a": DemoScraperA,
    "demo_b": DemoScraperB,
}


def load_config(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


async def run_one_scraper(cls: Type[Scraper], headless: bool, sports: list[str]) -> list[Game]:
    try:
        async with cls(headless=headless) as s:
            return await s.scrape(sports)
    except Exception as e:
        print_warning(f"{cls.NAME}: scraper crashed: {e}")
        return []


async def run_cycle(config: dict, state: AlertedState) -> None:
    sportsbooks: list[str] = config["sportsbooks"]
    sports: list[str] = config["sports"]
    headless: bool = config.get("headless", True)
    total_stake: float = float(config["total_stake_per_arb"])
    min_roi: float = float(config["min_roi_pct"])
    min_stake: float = float(config["min_stake"])

    started = time.perf_counter()

    scraper_classes = []
    for name in sportsbooks:
        cls = SCRAPER_REGISTRY.get(name)
        if cls is None:
            print_warning(f"unknown sportsbook in config: {name}")
            continue
        scraper_classes.append(cls)

    results = await asyncio.gather(
        *(run_one_scraper(cls, headless, sports) for cls in scraper_classes)
    )
    games: list[Game] = [g for batch in results for g in batch]

    canonical = normalize_games(games)
    arbs = find_arbs(canonical, total_stake=total_stake,
                     min_roi_pct=min_roi, min_stake=min_stake)

    new_arbs = [a for a in arbs if state.is_new(a)]
    for arb in new_arbs:
        print_arb(arb)
        state.mark(arb)

    elapsed = time.perf_counter() - started
    print_cycle_summary(num_games=len(canonical), num_arbs=len(new_arbs), elapsed_s=elapsed)


async def main_async(config_path: Path, once: bool) -> int:
    config = load_config(config_path)
    logging.basicConfig(
        level=config.get("log_level", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    state = AlertedState(ttl_seconds=int(config.get("alert_ttl_seconds", 600)))
    poll = int(config.get("poll_interval_seconds", 60))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    print_info(
        f"Arb bot starting  •  books={config['sportsbooks']}  "
        f"sports={config['sports']}  poll={poll}s  total_stake=${config['total_stake_per_arb']}"
    )

    while not stop.is_set():
        try:
            await run_cycle(config, state)
        except Exception as e:
            print_error(f"cycle failed: {e}")
        if once:
            break
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll)
        except asyncio.TimeoutError:
            continue

    print_info("Shutting down.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sports betting arbitrage scanner")
    parser.add_argument("--config", default="config.yaml", type=Path)
    parser.add_argument("--once", action="store_true", help="Run a single cycle then exit")
    args = parser.parse_args()
    if not args.config.exists():
        print_error(f"config file not found: {args.config}")
        return 2
    return asyncio.run(main_async(args.config, args.once))


if __name__ == "__main__":
    sys.exit(main())
