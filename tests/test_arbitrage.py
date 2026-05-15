"""Anchors the math against the two screenshot examples the user provided."""
from datetime import datetime, timezone

import pytest

from src.arbitrage import (
    compute_strategy_a,
    compute_strategy_b,
    find_arbs,
    find_best_arb_for_game,
    is_arbitrage,
)
from src.models import CanonicalGame, OddsLine
from src.odds_utils import american_to_decimal


CELTICS_DEC = american_to_decimal(150)   # 2.50
KNICKS_DEC = american_to_decimal(-125)   # 1.80


class TestStrategyA:
    """Strategy A screenshot: +150 / -125 with $100 total → $4.65 profit, 4.65% ROI."""

    def test_screenshot_example(self):
        s = compute_strategy_a(CELTICS_DEC, KNICKS_DEC, 100.0)
        assert s.home_stake == pytest.approx(41.86, abs=0.01)
        assert s.away_stake == pytest.approx(58.14, abs=0.01)
        assert s.total_stake == pytest.approx(100.00, abs=0.01)
        assert s.guaranteed_return == pytest.approx(104.65, abs=0.01)
        assert s.profit == pytest.approx(4.65, abs=0.01)
        assert s.roi_pct == pytest.approx(4.65, abs=0.01)

    def test_no_arb_when_implied_sum_geq_1(self):
        # Both -110 (standard vig): no arb
        d = american_to_decimal(-110)
        assert not is_arbitrage(d, d)
        s = compute_strategy_a(d, d, 100.0)
        # When no arb, return < total_stake → negative profit
        assert s.profit < 0

    def test_scales_linearly(self):
        s50 = compute_strategy_a(CELTICS_DEC, KNICKS_DEC, 50.0)
        s100 = compute_strategy_a(CELTICS_DEC, KNICKS_DEC, 100.0)
        assert s50.profit == pytest.approx(s100.profit / 2, abs=0.01)
        assert s50.roi_pct == pytest.approx(s100.roi_pct, abs=0.01)


class TestStrategyB:
    """Strategy B screenshot: same odds, favor Celtics → $11.10 profit if Celtics win,
    break-even if Knicks win, $44.44 / $55.56 stakes."""

    def test_screenshot_example_favor_home(self):
        # In the screenshot, Celtics is the favored side. Treat Celtics as "home".
        s = compute_strategy_b(
            home_decimal=CELTICS_DEC,
            away_decimal=KNICKS_DEC,
            total_stake=100.0,
            favored_side="home",
        )
        assert s.favored_stake == pytest.approx(44.44, abs=0.01)
        assert s.other_stake == pytest.approx(55.56, abs=0.01)
        # Screenshot says $111.10 but that's $44.44 * 2.50 with prior rounding;
        # exact math is 44.444... * 2.50 = 111.111... → 111.11. Accept either.
        assert s.favored_win_return == pytest.approx(111.10, abs=0.02)
        assert s.other_win_return == pytest.approx(100.00, abs=0.01)
        assert s.favored_win_profit == pytest.approx(11.10, abs=0.02)
        assert s.other_win_profit == pytest.approx(0.00, abs=0.01)

    def test_favor_away_swaps_correctly(self):
        s = compute_strategy_b(
            home_decimal=CELTICS_DEC,
            away_decimal=KNICKS_DEC,
            total_stake=100.0,
            favored_side="away",
        )
        # Favoring the Knicks (-125, d=1.80): other_stake covers Celtics at 2.50
        # other_stake = 100 / 2.50 = 40; favored_stake = 60
        assert s.other_stake == pytest.approx(40.00, abs=0.01)
        assert s.favored_stake == pytest.approx(60.00, abs=0.01)
        assert s.favored_win_return == pytest.approx(108.00, abs=0.01)  # 60 * 1.80

    def test_strategy_b_non_arb_loses_on_favored_side(self):
        # Strategy B sizes other_stake = T/d_other so the OTHER side always returns T
        # (break-even). When there's no real arb, the favored side now under-returns
        # — that's the "small loss" risk the screenshot text warns about.
        d = american_to_decimal(-110)  # 1.9091
        s = compute_strategy_b(home_decimal=d, away_decimal=d, total_stake=100.0,
                               favored_side="home")
        assert s.other_win_return == pytest.approx(100.00, abs=0.01)
        # No edge ⇒ favored-side return < total stake (concretely $90.91)
        assert s.favored_win_return < 100.0
        assert s.favored_win_profit < 0


class TestArbDetectionAcrossBooks:
    def _make_game(self, lines: list[OddsLine]) -> CanonicalGame:
        return CanonicalGame(
            sport="nba",
            home_team="Boston Celtics",
            away_team="New York Knicks",
            commence_time=datetime(2026, 5, 20, 19, 0, tzinfo=timezone.utc),
            lines=lines,
        )

    def test_finds_arb_across_two_books(self):
        # DK has Celtics +150; FD has Knicks -125 — this is an arb
        # (Strategy A screenshot scenario)
        dk_home = OddsLine(sportsbook="draftkings", side="home", team="Boston Celtics",
                           american_odds=150, decimal_odds=CELTICS_DEC)
        dk_away = OddsLine(sportsbook="draftkings", side="away", team="New York Knicks",
                           american_odds=-180, decimal_odds=american_to_decimal(-180))
        fd_home = OddsLine(sportsbook="fanduel", side="home", team="Boston Celtics",
                           american_odds=130, decimal_odds=american_to_decimal(130))
        fd_away = OddsLine(sportsbook="fanduel", side="away", team="New York Knicks",
                           american_odds=-125, decimal_odds=KNICKS_DEC)
        game = self._make_game([dk_home, dk_away, fd_home, fd_away])

        arb = find_best_arb_for_game(game, total_stake=100.0)
        assert arb is not None
        assert arb.home_line.sportsbook == "draftkings"  # best home (+150)
        assert arb.away_line.sportsbook == "fanduel"      # best away (-125 = 1.80)
        assert arb.profit == pytest.approx(4.65, abs=0.01)
        assert arb.roi_pct == pytest.approx(4.65, abs=0.01)

    def test_no_arb_when_only_one_book(self):
        # Same book on both sides → not a real arb (you can't bet against yourself)
        dk_home = OddsLine(sportsbook="draftkings", side="home", team="Boston Celtics",
                           american_odds=150, decimal_odds=CELTICS_DEC)
        dk_away = OddsLine(sportsbook="draftkings", side="away", team="New York Knicks",
                           american_odds=-125, decimal_odds=KNICKS_DEC)
        game = self._make_game([dk_home, dk_away])
        assert find_best_arb_for_game(game, total_stake=100.0) is None

    def test_no_arb_when_implied_sum_geq_1(self):
        d = american_to_decimal(-110)
        dk_home = OddsLine(sportsbook="draftkings", side="home", team="Boston Celtics",
                           american_odds=-110, decimal_odds=d)
        fd_away = OddsLine(sportsbook="fanduel", side="away", team="New York Knicks",
                           american_odds=-110, decimal_odds=d)
        game = self._make_game([dk_home, fd_away])
        assert find_best_arb_for_game(game, total_stake=100.0) is None

    def test_find_arbs_filters_min_roi(self):
        dk_home = OddsLine(sportsbook="draftkings", side="home", team="Boston Celtics",
                           american_odds=150, decimal_odds=CELTICS_DEC)
        fd_away = OddsLine(sportsbook="fanduel", side="away", team="New York Knicks",
                           american_odds=-125, decimal_odds=KNICKS_DEC)
        game = self._make_game([dk_home, fd_away])
        assert find_arbs([game], total_stake=100.0, min_roi_pct=10.0) == []
        assert len(find_arbs([game], total_stake=100.0, min_roi_pct=1.0)) == 1
