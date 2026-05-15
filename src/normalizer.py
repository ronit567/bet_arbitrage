"""Match games across sportsbooks.

Team names vary across books ("LA Lakers" vs "Los Angeles Lakers"). This module:
  1) maps known aliases to a canonical name,
  2) falls back to fuzzy matching for unknowns,
  3) groups Games from multiple books into CanonicalGame buckets keyed by
     (sport, normalized team pair, kickoff date).
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta

from rapidfuzz import fuzz

from .models import CanonicalGame, Game, OddsLine


# Alias map: any of the aliases on the left → canonical name on the right.
# Extend as you discover new variants in scraped data.
TEAM_ALIASES: dict[str, str] = {
    # NBA
    "la lakers": "Los Angeles Lakers",
    "los angeles lakers": "Los Angeles Lakers",
    "lakers": "Los Angeles Lakers",
    "la clippers": "Los Angeles Clippers",
    "los angeles clippers": "Los Angeles Clippers",
    "clippers": "Los Angeles Clippers",
    "ny knicks": "New York Knicks",
    "new york knicks": "New York Knicks",
    "knicks": "New York Knicks",
    "boston celtics": "Boston Celtics",
    "celtics": "Boston Celtics",
    "golden state warriors": "Golden State Warriors",
    "gs warriors": "Golden State Warriors",
    "warriors": "Golden State Warriors",
    "philadelphia 76ers": "Philadelphia 76ers",
    "philadelphia sixers": "Philadelphia 76ers",
    "sixers": "Philadelphia 76ers",
    "76ers": "Philadelphia 76ers",
    # NFL
    "ny giants": "New York Giants",
    "new york giants": "New York Giants",
    "ny jets": "New York Jets",
    "new york jets": "New York Jets",
    "la rams": "Los Angeles Rams",
    "los angeles rams": "Los Angeles Rams",
    "la chargers": "Los Angeles Chargers",
    "los angeles chargers": "Los Angeles Chargers",
    # MLB
    "ny yankees": "New York Yankees",
    "new york yankees": "New York Yankees",
    "ny mets": "New York Mets",
    "new york mets": "New York Mets",
    "la dodgers": "Los Angeles Dodgers",
    "los angeles dodgers": "Los Angeles Dodgers",
    "la angels": "Los Angeles Angels",
    "los angeles angels": "Los Angeles Angels",
    # Soccer (a tiny sample — expand as needed)
    "man utd": "Manchester United",
    "manchester united": "Manchester United",
    "man city": "Manchester City",
    "manchester city": "Manchester City",
}


_PUNCT_RE = re.compile(r"[^\w\s]")


def _slug(name: str) -> str:
    return _PUNCT_RE.sub("", name.lower()).strip()


def canonical_team(name: str, fuzzy_threshold: int = 88) -> str:
    """Return the canonical team name for `name`.

    1) Exact alias lookup on lowercased/de-punctuated name.
    2) Fuzzy match against alias keys; if best score >= threshold, use it.
    3) Fall back to the original name as the canonical (so unknown teams still
       match themselves across books, but won't merge with unrelated teams).
    """
    s = _slug(name)
    if s in TEAM_ALIASES:
        return TEAM_ALIASES[s]
    best_score = 0
    best_alias = None
    for alias in TEAM_ALIASES:
        score = fuzz.ratio(s, alias)
        if score > best_score:
            best_score = score
            best_alias = alias
    if best_alias is not None and best_score >= fuzzy_threshold:
        return TEAM_ALIASES[best_alias]
    return name.strip()


def _bucket_key(sport: str, home: str, away: str, when: datetime) -> tuple[str, str, str, str]:
    pair = tuple(sorted([home, away]))
    # Bucket by UTC date — handles minor kickoff-time drift across books.
    day = when.astimezone().date().isoformat()
    return (sport, pair[0], pair[1], day)


def normalize_games(games: list[Game], time_tolerance: timedelta = timedelta(hours=6)) -> list[CanonicalGame]:
    """Group raw per-book Games into CanonicalGames keyed by (sport, team pair, date).

    `time_tolerance` is a safety check: even within the same bucket, we won't merge
    games whose kickoff times differ by more than this (catches doubleheaders).
    """
    buckets: dict[tuple, list[Game]] = defaultdict(list)
    for g in games:
        home = canonical_team(g.home_team)
        away = canonical_team(g.away_team)
        key = _bucket_key(g.sport, home, away, g.commence_time)
        buckets[key].append(
            Game(
                sportsbook=g.sportsbook,
                sport=g.sport,
                home_team=home,
                away_team=away,
                commence_time=g.commence_time,
                home_line=OddsLine(
                    sportsbook=g.home_line.sportsbook,
                    side="home",
                    team=home,
                    american_odds=g.home_line.american_odds,
                    decimal_odds=g.home_line.decimal_odds,
                ),
                away_line=OddsLine(
                    sportsbook=g.away_line.sportsbook,
                    side="away",
                    team=away,
                    american_odds=g.away_line.american_odds,
                    decimal_odds=g.away_line.decimal_odds,
                ),
            )
        )

    out: list[CanonicalGame] = []
    for key, group in buckets.items():
        ref_time = group[0].commence_time
        compatible = [g for g in group if abs(g.commence_time - ref_time) <= time_tolerance]
        sport, t1, t2, _ = key
        # Choose the home/away orientation from the first game we saw for this bucket.
        first = compatible[0]
        lines: list[OddsLine] = []
        for g in compatible:
            if g.home_team == first.home_team:
                lines.append(g.home_line)
                lines.append(g.away_line)
            else:
                # Flip: this book reversed home/away. Re-tag sides accordingly.
                lines.append(OddsLine(
                    sportsbook=g.sportsbook, side="home", team=first.home_team,
                    american_odds=g.away_line.american_odds,
                    decimal_odds=g.away_line.decimal_odds,
                ))
                lines.append(OddsLine(
                    sportsbook=g.sportsbook, side="away", team=first.away_team,
                    american_odds=g.home_line.american_odds,
                    decimal_odds=g.home_line.decimal_odds,
                ))
        out.append(CanonicalGame(
            sport=sport,
            home_team=first.home_team,
            away_team=first.away_team,
            commence_time=ref_time,
            lines=lines,
        ))
    return out
