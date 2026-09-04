from __future__ import annotations

import pytest
from typer.testing import CliRunner

from github_admin import github_api
from github_admin.cli import app
from github_admin.github_api import RepoInfo

runner = CliRunner()


def _repo() -> RepoInfo:
    return RepoInfo(
        owner="octocat",
        name="widget",
        full_name="octocat/widget",
        description="a widget",
        visibility="public",
        is_fork=False,
        archived=False,
        license="MIT",
        has_readme=True,
        has_claude_md=True,
        has_src_layout=True,
        has_tests_dir=True,
        has_gitignore=True,
        has_ci_config=True,
        has_pyproject=True,
        branch_protected=True,
        contributors=2,
        topics=["cli"],
        stars=1,
        forks=0,
        open_issues=0,
        default_branch="main",
        created="2020-01-01",
        updated="2024-01-01",
        pushed="2024-01-01",
        url="https://github.com/octocat/widget",
    )


def test_report_prints_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_api, "resolve_token", lambda token_env="GITHUB_TOKEN": "fake-token")
    monkeypatch.setattr(github_api, "fetch_repos", lambda **kwargs: [_repo()])

    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "octocat/widget" in result.output


def test_report_errors_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_api, "resolve_token", lambda token_env="GITHUB_TOKEN": None)

    result = runner.invoke(app, [])
    assert result.exit_code == 1
    assert "no GitHub token found" in result.output


def test_report_writes_html(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    monkeypatch.setattr(github_api, "resolve_token", lambda token_env="GITHUB_TOKEN": "fake-token")
    monkeypatch.setattr(github_api, "fetch_repos", lambda **kwargs: [_repo()])

    out_path = Path(str(tmp_path)) / "report.html"
    result = runner.invoke(app, ["--html", str(out_path)])
    assert result.exit_code == 0
    assert out_path.exists()
    assert "octocat/widget" in out_path.read_text()
