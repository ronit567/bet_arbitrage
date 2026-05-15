"""Fixture scrapers that emit hand-crafted games — used to verify the full
detect→alert pipeline without depending on live sportsbook DOM stability.

Run with sportsbooks: [demo_a, demo_b] in config.yaml to see a known arb fire.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Game, OddsLine
from ..odds_utils import american_to_decimal
from .base import Scraper


def _line(book: str, team: str, side: str, american: int) -> OddsLine:
    return OddsLine(
        sportsbook=book,
        side=side,  # type: ignore[arg-type]
        team=team,
        american_odds=american,
        decimal_odds=american_to_decimal(american),
    )


def _game(book: str, sport: str, home: str, away: str,
          home_odds: int, away_odds: int, when: datetime) -> Game:
    return Game(
        sportsbook=book,
        sport=sport,
        home_team=home,
        away_team=away,
        commence_time=when,
        home_line=_line(book, home, "home", home_odds),
        away_line=_line(book, away, "away", away_odds),
    )


class DemoScraperA(Scraper):
    NAME = "demo_a"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def scrape_sport(self, sport: str) -> list[Game]:
        if sport != "nba":
            return []
        kickoff = datetime.now(timezone.utc) + timedelta(hours=3)
        # Demo A posts Celtics at +150 (the screenshot's good price for the home side)
        return [_game("demo_a", "nba", "Boston Celtics", "New York Knicks",
                      home_odds=150, away_odds=-180, when=kickoff)]


class DemoScraperB(Scraper):
    NAME = "demo_b"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def scrape_sport(self, sport: str) -> list[Game]:
        if sport != "nba":
            return []
        kickoff = datetime.now(timezone.utc) + timedelta(hours=3)
        # Demo B posts Knicks at -125 (the screenshot's good price for the away side)
        return [_game("demo_b", "nba", "Boston Celtics", "New York Knicks",
                      home_odds=130, away_odds=-125, when=kickoff)]
