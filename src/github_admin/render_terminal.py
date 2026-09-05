"""Render health-check results as a colored table in the terminal."""

from __future__ import annotations

from collections import Counter

from rich.console import Console
from rich.table import Table

from github_admin.health import RepoHealth

__all__ = ["render"]

_CHECK = "[green]✓[/green]"
_CROSS = "[red]✗[/red]"
_UNKNOWN = "[dim]?[/dim]"


def _flag(ok: bool) -> str:
    return _CHECK if ok else _CROSS


def _flag_tri(ok: bool | None) -> str:
    if ok is None:
        return _UNKNOWN
    return _flag(ok)


def _primary_owner(results: list[RepoHealth]) -> str:
    """The most-represented owner -- see render_dashboard._primary_owner
    for why only non-primary-owner repos keep their owner/ prefix here.
    """
    counts = Counter(h.repo.owner for h in results)
    return counts.most_common(1)[0][0] if counts else ""


def render(results: list[RepoHealth], console: Console | None = None) -> None:
    """Print one table: worst (most issues) repos first."""
    if console is None:
        console = Console()
        if not console.is_terminal:
            # Piped/redirected output (including test capture) has no real
            # display-width constraint, so don't cramp it to the 80-column
            # fallback rich uses when it can't detect a terminal size.
            console.width = 140
    primary_owner = _primary_owner(results)
    title = f"github-admin -- {len(results)} repos" + (f" ({primary_owner})" if primary_owner else "")
    table = Table(title=title)

    # repo names get a fixed, unwrapped column so they stay legible, capped
    # so one long name can't squeeze every other column's header down to an
    # unreadable ellipsis; each other column gets a min_width matching its
    # own header so headers never truncate. Full issue text (which checks
    # failed) is a count here, not the full list -- that goes in the HTML
    # report, which has room for it. Repos owned by primary_owner show just
    # their name, not owner/name -- see _primary_owner.
    table.add_column("repo", no_wrap=True, min_width=22, max_width=40)
    table.add_column("readme", justify="center", min_width=6)
    table.add_column("claude.md", justify="center", min_width=9)
    table.add_column("protected", justify="center", min_width=9)
    table.add_column("license", justify="center", min_width=7)
    table.add_column("contrib", justify="right", min_width=7)
    table.add_column("forks", justify="right", min_width=5)
    table.add_column("desc", justify="center", min_width=4)
    table.add_column("topics", justify="center", min_width=6)
    table.add_column("pushed", no_wrap=True, min_width=10)
    table.add_column("issues", no_wrap=True, min_width=9)

    for h in results:
        r = h.repo
        display_name = r.name if r.owner == primary_owner else r.full_name
        name = f"[dim]{display_name}[/dim]" if r.archived else display_name
        if r.platform != "github":
            name += f" [dim]({r.platform})[/dim]"
        if r.archived:
            name += " [dim](archived)[/dim]"
        contributors = "?" if r.contributors is None else str(r.contributors)
        if h.is_healthy:
            issue_text = "[green]ok[/green]"
        else:
            n = h.issue_count
            issue_text = f"[yellow]{n} issue{'s' if n != 1 else ''}[/yellow]"
        table.add_row(
            name,
            _flag(r.has_readme),
            _flag(r.has_claude_md),
            _flag_tri(r.branch_protected),
            _flag(bool(r.license)),
            contributors,
            str(r.forks),
            _flag(bool(r.description)),
            _flag(bool(r.topics)),
            r.pushed,
            issue_text,
        )

    console.print(table)
    unhealthy = sum(1 for h in results if not h.is_healthy)
    console.print(f"\n{unhealthy} of {len(results)} repos have at least one issue.")
    console.print("[dim]pass --html PATH for the full detail on each issue[/dim]")
