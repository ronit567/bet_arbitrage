"""Abstract Scraper + shared patchright browser lifecycle.

Each concrete scraper subclasses `Scraper` and implements `scrape_sport()`,
which navigates to the sport's moneyline page and returns a list of Games.
The base class handles browser launch, stealth defaults, timeouts, and retries.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from ..models import Game

log = logging.getLogger(__name__)


class Scraper(ABC):
    """Subclasses set NAME and supply per-sport URLs / parsing logic."""

    NAME: str = "base"
    DEFAULT_TIMEOUT_MS: int = 30_000

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._browser: Any | None = None
        self._context: Any | None = None
        self._playwright: Any | None = None

    async def __aenter__(self) -> "Scraper":
        try:
            from patchright.async_api import async_playwright  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "patchright is not installed. Install with: "
                "`pip install patchright && patchright install chromium`"
            ) from e
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1366, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
        )
        self._context.set_default_timeout(self.DEFAULT_TIMEOUT_MS)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            log.warning("Error during scraper cleanup: %s", e)

    async def new_page(self) -> Any:
        assert self._context is not None, "Use Scraper as `async with`"
        return await self._context.new_page()

    @abstractmethod
    async def scrape_sport(self, sport: str) -> list[Game]:
        """Return all games (with moneyline odds) for `sport` on this book."""

    async def scrape(self, sports: list[str]) -> list[Game]:
        """Scrape all requested sports; tolerate per-sport failures."""
        results: list[Game] = []
        for sport in sports:
            try:
                games = await asyncio.wait_for(
                    self.scrape_sport(sport), timeout=self.DEFAULT_TIMEOUT_MS / 1000 * 2
                )
                log.info("%s/%s: %d games", self.NAME, sport, len(games))
                results.extend(games)
            except Exception as e:
                log.warning("%s/%s scrape failed: %s", self.NAME, sport, e)
        return results
