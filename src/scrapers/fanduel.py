"""FanDuel sportsbook scraper.

Same caveat as DraftKings: selectors are best-effort and will need tuning when
FanDuel changes their DOM. Each failure is logged and the pipeline continues.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from ..models import Game, OddsLine
from ..odds_utils import american_to_decimal
from .base import Scraper

log = logging.getLogger(__name__)


SPORT_URLS: dict[str, str] = {
    "nba": "https://sportsbook.fanduel.com/navigation/nba",
    "nfl": "https://sportsbook.fanduel.com/navigation/nfl",
    "mlb": "https://sportsbook.fanduel.com/navigation/mlb",
    "nhl": "https://sportsbook.fanduel.com/navigation/nhl",
    "ncaaf": "https://sportsbook.fanduel.com/navigation/college-football",
    "ncaab": "https://sportsbook.fanduel.com/navigation/college-basketball",
    "soccer_epl": "https://sportsbook.fanduel.com/navigation/english-premier-league",
    "soccer_uefa_cl": "https://sportsbook.fanduel.com/navigation/uefa-champions-league",
}


_AMERICAN_ODDS_RE = re.compile(r"^[+-]\d{3,5}$")


class FanDuelScraper(Scraper):
    NAME = "fanduel"

    async def scrape_sport(self, sport: str) -> list[Game]:
        url = SPORT_URLS.get(sport)
        if not url:
            log.warning("fanduel: no URL for sport %s", sport)
            return []

        page = await self.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            # FD groups events under [data-test-id="event-card"] (subject to change).
            await page.wait_for_selector('[data-test-id="event-card"]', timeout=15_000)
            cards = await page.query_selector_all('[data-test-id="event-card"]')

            games: list[Game] = []
            for card in cards:
                try:
                    game = await self._parse_card(card, sport)
                    if game:
                        games.append(game)
                except Exception as e:
                    log.debug("fanduel/%s: card parse failed: %s", sport, e)
            return games
        finally:
            await page.close()

    async def _parse_card(self, card, sport: str) -> Game | None:
        team_els = await card.query_selector_all('[data-test-id="event-card-team-name"]')
        if len(team_els) < 2:
            return None
        away_team = (await team_els[0].inner_text()).strip()
        home_team = (await team_els[1].inner_text()).strip()

        odds_els = await card.query_selector_all('[data-test-id="moneyline-odds"]')
        american: list[int] = []
        for el in odds_els:
            txt = (await el.inner_text()).strip().replace("−", "-")
            if _AMERICAN_ODDS_RE.match(txt):
                american.append(int(txt))
        if len(american) < 2:
            return None
        away_american, home_american = american[0], american[1]

        return Game(
            sportsbook=self.NAME,
            sport=sport,
            home_team=home_team,
            away_team=away_team,
            commence_time=datetime.now(timezone.utc),
            home_line=OddsLine(
                sportsbook=self.NAME, side="home", team=home_team,
                american_odds=home_american,
                decimal_odds=american_to_decimal(home_american),
            ),
            away_line=OddsLine(
                sportsbook=self.NAME, side="away", team=away_team,
                american_odds=away_american,
                decimal_odds=american_to_decimal(away_american),
            ),
        )
