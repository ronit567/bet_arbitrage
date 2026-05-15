"""Shared data contracts between scrapers, normalizer, detector, and alerts."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Side = Literal["home", "away"]


class OddsLine(BaseModel):
    """A single moneyline price posted by one sportsbook for one side of one game."""
    sportsbook: str
    side: Side
    team: str
    american_odds: int
    decimal_odds: float


class Game(BaseModel):
    """A game as seen by a single sportsbook, with both moneyline prices."""
    sportsbook: str
    sport: str
    home_team: str
    away_team: str
    commence_time: datetime
    home_line: OddsLine
    away_line: OddsLine


class CanonicalGame(BaseModel):
    """A game after normalization, with odds lines collected from every book that posted it."""
    sport: str
    home_team: str
    away_team: str
    commence_time: datetime
    lines: list[OddsLine] = Field(default_factory=list)


class ArbOpportunity(BaseModel):
    """A detected two-way moneyline arbitrage with computed Strategy A stakes."""
    sport: str
    home_team: str
    away_team: str
    commence_time: datetime

    home_line: OddsLine
    away_line: OddsLine

    total_stake: float
    home_stake: float
    away_stake: float
    guaranteed_return: float
    profit: float
    roi_pct: float

    def dedupe_key(self) -> str:
        return (
            f"{self.sport}|{self.home_team}|{self.away_team}|{self.commence_time.isoformat()}"
            f"|{self.home_line.sportsbook}:{self.home_line.american_odds}"
            f"|{self.away_line.sportsbook}:{self.away_line.american_odds}"
        )
