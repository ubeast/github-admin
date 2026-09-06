from __future__ import annotations

import pytest
from typer.testing import CliRunner

from repo_healthcheck import github_api, gitlab_api
from repo_healthcheck.cli import app
from repo_healthcheck.github_api import RepoInfo

runner = CliRunner()


def _repo(**overrides: object) -> RepoInfo:
    defaults: dict[str, object] = dict(
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
    defaults.update(overrides)
    return RepoInfo(**defaults)


def test_report_prints_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_api, "resolve_token", lambda token_env="GITHUB_TOKEN": "fake-token")
    monkeypatch.setattr(github_api, "fetch_repos", lambda **kwargs: [_repo()])

    result = runner.invoke(app, [])
    assert result.exit_code == 0
    # single-owner report: shown by short name, owner surfaced in the title instead
    assert "widget" in result.output
    assert "octocat" in result.output


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


def test_report_writes_markdown(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    monkeypatch.setattr(github_api, "resolve_token", lambda token_env="GITHUB_TOKEN": "fake-token")
    monkeypatch.setattr(github_api, "fetch_repos", lambda **kwargs: [_repo()])

    out_path = Path(str(tmp_path)) / "report.md"
    result = runner.invoke(app, ["--markdown", str(out_path)])
    assert result.exit_code == 0
    assert out_path.exists()
    text = out_path.read_text()
    assert text.startswith("# repo-healthcheck")
    assert "octocat/widget" in text


def test_report_merges_gitlab_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    gl_repo = _repo(
        owner="myteam", name="widget", full_name="myteam/widget", platform="gitlab",
        url="https://gitlab.com/myteam/widget",
    )
    monkeypatch.setattr(github_api, "resolve_token", lambda token_env="GITHUB_TOKEN": "fake-token")
    monkeypatch.setattr(github_api, "fetch_repos", lambda **kwargs: [_repo()])
    monkeypatch.setattr(gitlab_api, "resolve_token", lambda token_env="GITLAB_TOKEN": "fake-gl-token")
    monkeypatch.setattr(gitlab_api, "fetch_repos", lambda **kwargs: [gl_repo])

    result = runner.invoke(app, ["--gitlab"])
    assert result.exit_code == 0
    # One of the two tied owners is shown by short name, the other keeps its
    # owner/ prefix so the two "widget" repos aren't mistaken for each other.
    assert "widget" in result.output
    assert "octocat/widget" in result.output or "myteam/widget" in result.output


def test_report_errors_without_gitlab_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_api, "resolve_token", lambda token_env="GITHUB_TOKEN": "fake-token")
    monkeypatch.setattr(github_api, "fetch_repos", lambda **kwargs: [_repo()])
    monkeypatch.setattr(gitlab_api, "resolve_token", lambda token_env="GITLAB_TOKEN": None)

    result = runner.invoke(app, ["--gitlab"])
    assert result.exit_code == 1
    assert "no GitLab token found" in result.output
