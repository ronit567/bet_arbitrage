"""Pretty-print arbitrage opportunities to the terminal."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import ArbOpportunity

_console = Console()


def _fmt_american(n: int) -> str:
    return f"+{n}" if n > 0 else str(n)


def print_arb(arb: ArbOpportunity) -> None:
    kickoff = arb.commence_time.strftime("%Y-%m-%d %H:%M %Z").strip()
    header = (
        f"[bold green]ARB[/bold green]  {arb.sport.upper()}  "
        f"{arb.away_team} @ {arb.home_team}  "
        f"[dim]({kickoff})[/dim]"
    )
    table = Table(show_header=True, header_style="bold cyan", expand=False)
    table.add_column("Side")
    table.add_column("Team")
    table.add_column("Sportsbook")
    table.add_column("Odds", justify="right")
    table.add_column("Stake", justify="right")
    table.add_column("Return", justify="right")
    table.add_row(
        "HOME", arb.home_team, arb.home_line.sportsbook,
        _fmt_american(arb.home_line.american_odds),
        f"${arb.home_stake:.2f}",
        f"${arb.home_stake * arb.home_line.decimal_odds:.2f}",
    )
    table.add_row(
        "AWAY", arb.away_team, arb.away_line.sportsbook,
        _fmt_american(arb.away_line.american_odds),
        f"${arb.away_stake:.2f}",
        f"${arb.away_stake * arb.away_line.decimal_odds:.2f}",
    )
    summary = (
        f"[bold]Total stake:[/bold] ${arb.total_stake:.2f}    "
        f"[bold]Guaranteed return:[/bold] ${arb.guaranteed_return:.2f}    "
        f"[bold green]Profit:[/bold green] ${arb.profit:.2f} ({arb.roi_pct:.2f}% ROI)"
    )
    _console.print(Panel.fit(table, title=header, border_style="green"))
    _console.print(summary)
    _console.print()


def print_cycle_summary(num_games: int, num_arbs: int, elapsed_s: float) -> None:
    _console.print(
        f"[dim]Scanned {num_games} games  •  {num_arbs} arbs found  •  "
        f"{elapsed_s:.1f}s[/dim]"
    )


def print_info(msg: str) -> None:
    _console.print(f"[cyan]{msg}[/cyan]")


def print_warning(msg: str) -> None:
    _console.print(f"[yellow]{msg}[/yellow]")


def print_error(msg: str) -> None:
    _console.print(f"[red]{msg}[/red]")
