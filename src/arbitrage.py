"""Arbitrage detection and stake sizing (Strategy A and Strategy B)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import ArbOpportunity, CanonicalGame, OddsLine, Side


@dataclass(frozen=True)
class StrategyAStakes:
    """Equal-payout stakes: same return regardless of which side wins."""
    home_stake: float
    away_stake: float
    total_stake: float
    guaranteed_return: float
    profit: float
    roi_pct: float


@dataclass(frozen=True)
class StrategyBStakes:
    """Weighted stakes: bigger upside on the favored side, break-even floor on the other."""
    favored_side: Side
    favored_stake: float
    other_stake: float
    total_stake: float
    favored_win_return: float
    other_win_return: float
    favored_win_profit: float
    other_win_profit: float


def is_arbitrage(home_decimal: float, away_decimal: float) -> bool:
    return (1.0 / home_decimal + 1.0 / away_decimal) < 1.0


def implied_sum(home_decimal: float, away_decimal: float) -> float:
    return 1.0 / home_decimal + 1.0 / away_decimal


def compute_strategy_a(
    home_decimal: float,
    away_decimal: float,
    total_stake: float,
) -> StrategyAStakes:
    """Stake both sides so the return is identical whichever side wins.

    stake_home = T * (1/d_home) / (1/d_home + 1/d_away)
    stake_away = T - stake_home
    return    = stake_home * d_home == stake_away * d_away (when implied_sum < 1)
    """
    if total_stake <= 0:
        raise ValueError("total_stake must be positive")
    inv_home = 1.0 / home_decimal
    inv_away = 1.0 / away_decimal
    denom = inv_home + inv_away
    home_stake = total_stake * inv_home / denom
    away_stake = total_stake - home_stake
    guaranteed_return = home_stake * home_decimal
    profit = guaranteed_return - total_stake
    roi_pct = profit / total_stake * 100.0
    return StrategyAStakes(
        home_stake=round(home_stake, 2),
        away_stake=round(away_stake, 2),
        total_stake=round(total_stake, 2),
        guaranteed_return=round(guaranteed_return, 2),
        profit=round(profit, 2),
        roi_pct=round(roi_pct, 2),
    )


def compute_strategy_b(
    home_decimal: float,
    away_decimal: float,
    total_stake: float,
    favored_side: Side,
) -> StrategyBStakes:
    """Skew stakes toward favored side; break-even floor on the other.

    Sized so that other-side win exactly returns total_stake (break-even):
      other_stake = T / d_other
      favored_stake = T - other_stake
    Favored-side win yields favored_stake * d_favored.
    """
    if total_stake <= 0:
        raise ValueError("total_stake must be positive")
    if favored_side == "home":
        d_fav, d_other = home_decimal, away_decimal
    else:
        d_fav, d_other = away_decimal, home_decimal

    other_stake = total_stake / d_other
    favored_stake = total_stake - other_stake
    if favored_stake <= 0:
        raise ValueError(
            "Strategy B requires a true arbitrage (implied_sum < 1); "
            f"got home={home_decimal} away={away_decimal}"
        )
    favored_win_return = favored_stake * d_fav
    other_win_return = other_stake * d_other  # == total_stake by construction
    return StrategyBStakes(
        favored_side=favored_side,
        favored_stake=round(favored_stake, 2),
        other_stake=round(other_stake, 2),
        total_stake=round(total_stake, 2),
        favored_win_return=round(favored_win_return, 2),
        other_win_return=round(other_win_return, 2),
        favored_win_profit=round(favored_win_return - total_stake, 2),
        other_win_profit=round(other_win_return - total_stake, 2),
    )


def find_best_arb_for_game(
    game: CanonicalGame,
    total_stake: float,
) -> ArbOpportunity | None:
    """For a canonical game, pick the best home line and best away line across all books.

    Two-way arb requires the two lines to come from DIFFERENT sportsbooks — otherwise
    you'd just be betting against yourself at one book.
    """
    home_lines = [ln for ln in game.lines if ln.side == "home"]
    away_lines = [ln for ln in game.lines if ln.side == "away"]
    if not home_lines or not away_lines:
        return None

    best: tuple[OddsLine, OddsLine] | None = None
    best_sum = 1.0  # anything >= 1 is not an arb
    for h in home_lines:
        for a in away_lines:
            if h.sportsbook == a.sportsbook:
                continue
            s = implied_sum(h.decimal_odds, a.decimal_odds)
            if s < best_sum:
                best_sum = s
                best = (h, a)

    if best is None or best_sum >= 1.0:
        return None

    h, a = best
    stakes = compute_strategy_a(h.decimal_odds, a.decimal_odds, total_stake)
    return ArbOpportunity(
        sport=game.sport,
        home_team=game.home_team,
        away_team=game.away_team,
        commence_time=game.commence_time,
        home_line=h,
        away_line=a,
        total_stake=stakes.total_stake,
        home_stake=stakes.home_stake,
        away_stake=stakes.away_stake,
        guaranteed_return=stakes.guaranteed_return,
        profit=stakes.profit,
        roi_pct=stakes.roi_pct,
    )


def find_arbs(
    games: Iterable[CanonicalGame],
    total_stake: float,
    min_roi_pct: float = 0.0,
    min_stake: float = 0.0,
) -> list[ArbOpportunity]:
    """Run arb detection across many canonical games, applying ROI and min-stake filters."""
    out: list[ArbOpportunity] = []
    for g in games:
        arb = find_best_arb_for_game(g, total_stake)
        if arb is None:
            continue
        if arb.roi_pct < min_roi_pct:
            continue
        if arb.home_stake < min_stake or arb.away_stake < min_stake:
            continue
        out.append(arb)
    out.sort(key=lambda x: x.roi_pct, reverse=True)
    return out
