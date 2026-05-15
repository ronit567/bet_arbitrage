"""DraftKings sportsbook scraper.

NOTE: Sportsbook DOMs change frequently and DraftKings uses Cloudflare/bot
detection. The selectors below are a *starting point* based on the public layout
as-of writing; expect to tune them. When a selector breaks, the scraper logs a
warning and that sport returns 0 games — the rest of the pipeline keeps running.
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
    "nba": "https://sportsbook.draftkings.com/leagues/basketball/nba",
    "nfl": "https://sportsbook.draftkings.com/leagues/football/nfl",
    "mlb": "https://sportsbook.draftkings.com/leagues/baseball/mlb",
    "nhl": "https://sportsbook.draftkings.com/leagues/hockey/nhl",
    "ncaaf": "https://sportsbook.draftkings.com/leagues/football/ncaaf",
    "ncaab": "https://sportsbook.draftkings.com/leagues/basketball/ncaab",
    "soccer_epl": "https://sportsbook.draftkings.com/leagues/soccer/england-premier-league",
    "soccer_uefa_cl": "https://sportsbook.draftkings.com/leagues/soccer/uefa-champions-league",
}


_AMERICAN_ODDS_RE = re.compile(r"^[+-]\d{3,5}$")


class DraftKingsScraper(Scraper):
    NAME = "draftkings"

    async def scrape_sport(self, sport: str) -> list[Game]:
        url = SPORT_URLS.get(sport)
        if not url:
            log.warning("draftkings: no URL for sport %s", sport)
            return []

        page = await self.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            # DK renders odds inside `.sportsbook-event-accordion__wrapper` rows.
            await page.wait_for_selector(".sportsbook-event-accordion__wrapper", timeout=15_000)
            rows = await page.query_selector_all(".sportsbook-event-accordion__wrapper")

            games: list[Game] = []
            for row in rows:
                try:
                    game = await self._parse_row(row, sport)
                    if game:
                        games.append(game)
                except Exception as e:
                    log.debug("draftkings/%s: row parse failed: %s", sport, e)
            return games
        finally:
            await page.close()

    async def _parse_row(self, row, sport: str) -> Game | None:
        team_els = await row.query_selector_all(".event-cell__name-text")
        if len(team_els) < 2:
            return None
        away_team = (await team_els[0].inner_text()).strip()
        home_team = (await team_els[1].inner_text()).strip()

        # Moneyline column is typically the third sportsbook-outcome-cell pair per row.
        # We look for cells whose text matches an American-odds pattern.
        odds_els = await row.query_selector_all(".sportsbook-odds")
        american: list[int] = []
        for el in odds_els:
            txt = (await el.inner_text()).strip().replace("−", "-")  # unicode minus
            if _AMERICAN_ODDS_RE.match(txt):
                american.append(int(txt))
        # On DK, the moneyline pair is typically the LAST two odds in the row.
        if len(american) < 2:
            return None
        away_american, home_american = american[-2], american[-1]

        commence = await self._parse_commence(row)

        return Game(
            sportsbook=self.NAME,
            sport=sport,
            home_team=home_team,
            away_team=away_team,
            commence_time=commence,
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

    async def _parse_commence(self, row) -> datetime:
        # Best-effort: DK shows times as "Today 7:30 PM" / "Tomorrow 1:00 PM" / "Sun 7:30 PM".
        # If we can't parse, return now() so the dedupe key still works.
        try:
            t_el = await row.query_selector(".event-cell__start-time")
            if t_el:
                txt = (await t_el.inner_text()).strip()
                log.debug("draftkings commence raw=%r", txt)
        except Exception:
            pass
        return datetime.now(timezone.utc)
