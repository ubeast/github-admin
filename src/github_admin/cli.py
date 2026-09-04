"""``github-admin`` CLI: consolidate your GitHub repos into one health-check view."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from github_admin import github_api, health, render_dashboard, render_html, render_terminal

app = typer.Typer(add_completion=False, no_args_is_help=False)
_err = Console(stderr=True)


@app.callback(invoke_without_command=True)
def report(
    owner: Annotated[
        str | None,
        typer.Option(help="Only this user/org's public repos, instead of everything the token can see."),
    ] = None,
    token_env: Annotated[
        str, typer.Option(help="Env var holding the GitHub token, checked before `gh auth token`.")
    ] = "GITHUB_TOKEN",
    stale_days: Annotated[
        int, typer.Option(help="Flag repos with no push in this many days as stale.")
    ] = health.DEFAULT_STALE_DAYS,
    html: Annotated[
        Path | None, typer.Option(help="Also write a plain static HTML report to this path.")
    ] = None,
    dashboard: Annotated[
        Path | None,
        typer.Option(help="Also write an interactive HTML dashboard to this path (filter + multi-column sort)."),
    ] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress fetch progress on stderr.")] = False,
) -> None:
    """Fetch every repo you can see and print a health-check table, worst first."""
    token = github_api.resolve_token(token_env)
    if not token and not owner:
        _err.print(
            "[red]error:[/red] no GitHub token found -- set GITHUB_TOKEN or run `gh auth login`"
        )
        raise typer.Exit(1)

    progress = None if quiet else (lambda msg: _err.print(f"[dim]{msg}[/dim]"))
    try:
        repos = github_api.fetch_repos(token=token, owner=owner, progress=progress)
    except github_api.ApiError as exc:
        _err.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1) from exc

    results = health.check_all(repos, stale_days=stale_days)
    render_terminal.render(results)

    if html is not None:
        html.write_text(render_html.render(results), encoding="utf-8")
        _err.print(f"\n[dim]wrote {html}[/dim]")

    if dashboard is not None:
        dashboard.write_text(render_dashboard.render(results), encoding="utf-8")
        _err.print(f"[dim]wrote {dashboard}[/dim]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
