from __future__ import annotations

import io

from rich.console import Console

from github_admin import render_terminal
from github_admin.github_api import RepoInfo
from github_admin.health import RepoHealth


def _repo(**overrides: object) -> RepoInfo:
    defaults: dict[str, object] = dict(
        owner="octocat",
        name="widget",
        full_name="octocat/widget",
        description="",
        visibility="public",
        is_fork=False,
        archived=False,
        license="",
        has_readme=False,
        contributors=1,
        topics=[],
        stars=0,
        forks=0,
        open_issues=0,
        default_branch="main",
        created="2020-01-01",
        updated="2024-01-01",
        pushed="2024-01-01",
        url="https://github.com/octocat/widget",
    )
    defaults.update(overrides)
    return RepoInfo(**defaults)  # type: ignore[arg-type]


def test_render_prints_repo_name_and_summary() -> None:
    result = RepoHealth(repo=_repo(), issues=["no README", "no license"])
    buf = io.StringIO()
    console = Console(file=buf, width=200)
    render_terminal.render([result], console=console)
    output = buf.getvalue()
    assert "octocat/widget" in output
    assert "2 issues" in output
    assert "1 of 1 repos have at least one issue." in output
