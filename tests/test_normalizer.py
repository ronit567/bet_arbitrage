from datetime import datetime, timezone

from src.models import Game, OddsLine
from src.normalizer import canonical_team, normalize_games
from src.odds_utils import american_to_decimal


class TestCanonicalTeam:
    def test_exact_alias(self):
        assert canonical_team("LA Lakers") == "Los Angeles Lakers"
        assert canonical_team("Lakers") == "Los Angeles Lakers"
        assert canonical_team("Los Angeles Lakers") == "Los Angeles Lakers"

    def test_punct_and_case_insensitive(self):
        assert canonical_team("L.A. Lakers") == "Los Angeles Lakers"
        assert canonical_team("LAKERS") == "Los Angeles Lakers"

    def test_fuzzy_handles_minor_typo(self):
        # "Bostn Celtics" should fuzzy-match "boston celtics"
        assert canonical_team("Bostn Celtics") == "Boston Celtics"

    def test_unknown_team_passes_through(self):
        assert canonical_team("Atlantis Mermaids") == "Atlantis Mermaids"

    def test_does_not_merge_unrelated_teams(self):
        # "Sparks" is not in the alias map and should NOT collapse to "Lakers"
        assert canonical_team("Sparks") != "Los Angeles Lakers"


def _make_game(book: str, home: str, away: str, hodds: int, aodds: int,
               commence: datetime, sport: str = "nba") -> Game:
    return Game(
        sportsbook=book,
        sport=sport,
        home_team=home,
        away_team=away,
        commence_time=commence,
        home_line=OddsLine(sportsbook=book, side="home", team=home,
                           american_odds=hodds, decimal_odds=american_to_decimal(hodds)),
        away_line=OddsLine(sportsbook=book, side="away", team=away,
                           american_odds=aodds, decimal_odds=american_to_decimal(aodds)),
    )


class TestNormalizeGames:
    def test_merges_same_game_across_books(self):
        t = datetime(2026, 5, 20, 19, 0, tzinfo=timezone.utc)
        dk = _make_game("draftkings", "Boston Celtics", "New York Knicks", 150, -180, t)
        fd = _make_game("fanduel", "Celtics", "Knicks", 130, -125, t)
        canon = normalize_games([dk, fd])
        assert len(canon) == 1
        cg = canon[0]
        assert cg.home_team == "Boston Celtics"
        assert cg.away_team == "New York Knicks"
        # 4 lines: home+away from each of 2 books
        assert len(cg.lines) == 4
        books = {ln.sportsbook for ln in cg.lines}
        assert books == {"draftkings", "fanduel"}

    def test_handles_flipped_home_away(self):
        # FanDuel lists the same matchup but with home/away swapped.
        t = datetime(2026, 5, 20, 19, 0, tzinfo=timezone.utc)
        dk = _make_game("draftkings", "Boston Celtics", "New York Knicks", 150, -180, t)
        fd = _make_game("fanduel", "New York Knicks", "Boston Celtics", -125, 130, t)
        canon = normalize_games([dk, fd])
        assert len(canon) == 1
        cg = canon[0]
        # Lines should still align: Celtics-side from DK is +150, Celtics-side from FD is +130
        celtics_lines = [ln for ln in cg.lines if ln.team == "Boston Celtics"]
        knicks_lines = [ln for ln in cg.lines if ln.team == "New York Knicks"]
        assert len(celtics_lines) == 2
        assert len(knicks_lines) == 2
        # Verify DK Celtics is the +150 line
        dk_celtics = next(ln for ln in celtics_lines if ln.sportsbook == "draftkings")
        assert dk_celtics.american_odds == 150

    def test_different_games_stay_separate(self):
        t = datetime(2026, 5, 20, 19, 0, tzinfo=timezone.utc)
        g1 = _make_game("draftkings", "Boston Celtics", "New York Knicks", 150, -180, t)
        g2 = _make_game("draftkings", "Los Angeles Lakers", "Golden State Warriors", 110, -130, t)
        canon = normalize_games([g1, g2])
        assert len(canon) == 2
