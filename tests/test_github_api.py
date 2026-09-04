from __future__ import annotations

import pytest

from github_admin import github_api


def test_parse_link_header() -> None:
    value = '<https://x/p?page=2>; rel="next", <https://x/p?page=9>; rel="last"'
    assert github_api._parse_link_header(value) == {
        "next": "https://x/p?page=2",
        "last": "https://x/p?page=9",
    }


def test_parse_link_header_empty() -> None:
    assert github_api._parse_link_header(None) == {}


def test_last_page_from_link() -> None:
    value = '<https://x?page=1&per_page=1>; rel="last"'
    assert github_api._last_page_from_link(value) == 1
    assert github_api._last_page_from_link(None) is None


def test_date_truncates_iso_timestamp() -> None:
    assert github_api._date("2024-06-07T08:09:10Z") == "2024-06-07"
    assert github_api._date("") == ""
    assert github_api._date(None) == ""


def test_resolve_token_prefers_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    assert github_api.resolve_token() == "env-token"


def test_resolve_token_falls_back_to_gh_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/gh")

    class _Result:
        stdout = "gh-cli-token\n"

    monkeypatch.setattr("subprocess.run", lambda *a, **k: _Result())
    assert github_api.resolve_token() == "gh-cli-token"


def test_resolve_token_none_when_no_token_and_no_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert github_api.resolve_token() is None


def test_to_repo_info_maps_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_api, "_has_readme", lambda full_name, headers: True)
    monkeypatch.setattr(github_api, "_contributor_count", lambda full_name, headers: 3)

    raw = {
        "name": "widget",
        "full_name": "octocat/widget",
        "owner": {"login": "octocat"},
        "description": "a widget",
        "private": False,
        "fork": False,
        "archived": False,
        "language": "Python",
        "stargazers_count": 12,
        "forks_count": 3,
        "open_issues_count": 1,
        "topics": ["cli"],
        "license": {"spdx_id": "MIT"},
        "default_branch": "main",
        "created_at": "2020-01-02T03:04:05Z",
        "updated_at": "2024-06-07T08:09:10Z",
        "pushed_at": "2024-06-06T00:00:00Z",
        "html_url": "https://github.com/octocat/widget",
    }
    rec = github_api._to_repo_info(raw, headers={})
    assert rec.owner == "octocat"
    assert rec.full_name == "octocat/widget"
    assert rec.license == "MIT"
    assert rec.has_readme is True
    assert rec.contributors == 3
    assert rec.stars == 12
    assert rec.created == "2020-01-02"


def test_fetch_repos_requires_token_or_owner() -> None:
    with pytest.raises(github_api.ApiError):
        github_api.fetch_repos(token=None, owner=None)
