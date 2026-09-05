from __future__ import annotations

import pytest

from repo_healthcheck import github_api


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


def test_root_listing_splits_files_and_dirs(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        {"name": "README.md", "type": "file"},
        {"name": "CLAUDE.md", "type": "file"},
        {"name": ".gitignore", "type": "file"},
        {"name": "pyproject.toml", "type": "file"},
        {"name": "src", "type": "dir"},
        {"name": "tests", "type": "dir"},
        {"name": ".github", "type": "dir"},
    ]
    monkeypatch.setattr(github_api, "_get_json", lambda url, headers: (entries, {}))
    files, dirs = github_api._root_listing("octocat/widget", headers={})
    assert files == {"readme.md", "claude.md", ".gitignore", "pyproject.toml"}
    assert dirs == {"src", "tests", ".github"}


def test_root_listing_empty_on_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(url: str, headers: dict[str, str]) -> None:
        raise github_api.ApiError("404")

    monkeypatch.setattr(github_api, "_get_json", _raise)
    files, dirs = github_api._root_listing("octocat/widget", headers={})
    assert files == set()
    assert dirs == set()


def test_branch_protection_false_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_api, "_request", lambda url, headers: (404, {}, b""))
    assert github_api._branch_protection("octocat/widget", "main", headers={}) is False


def test_branch_protection_unknown_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_api, "_request", lambda url, headers: (403, {}, b""))
    assert github_api._branch_protection("octocat/widget", "main", headers={}) is None


def test_branch_protection_true_when_force_push_and_deletion_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b'{"allow_force_pushes": {"enabled": false}, "allow_deletions": {"enabled": false}}'
    monkeypatch.setattr(github_api, "_request", lambda url, headers: (200, {}, body))
    assert github_api._branch_protection("octocat/widget", "main", headers={}) is True


def test_branch_protection_false_when_force_push_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b'{"allow_force_pushes": {"enabled": true}, "allow_deletions": {"enabled": false}}'
    monkeypatch.setattr(github_api, "_request", lambda url, headers: (200, {}, body))
    assert github_api._branch_protection("octocat/widget", "main", headers={}) is False


def test_branch_protection_none_without_branch_name() -> None:
    assert github_api._branch_protection("octocat/widget", "", headers={}) is None


def test_to_repo_info_maps_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        github_api,
        "_root_listing",
        lambda full_name, headers: ({"readme.md", "claude.md", "pyproject.toml"}, {"src"}),
    )
    monkeypatch.setattr(github_api, "_contributor_count", lambda full_name, headers: 3)
    monkeypatch.setattr(github_api, "_branch_protection", lambda full_name, branch, headers: True)

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
    assert rec.language == "Python"
    assert rec.has_readme is True
    assert rec.has_claude_md is True
    assert rec.has_src_layout is True
    assert rec.has_tests_dir is False
    assert rec.has_pyproject is True
    assert rec.branch_protected is True
    assert rec.contributors == 3
    assert rec.stars == 12
    assert rec.created == "2020-01-02"


def test_gnu_variant_from_text_identifies_gpl_family() -> None:
    assert github_api._gnu_variant_from_text("                    GNU GENERAL PUBLIC LICENSE\n") == "GPL"
    assert github_api._gnu_variant_from_text("GNU LESSER GENERAL PUBLIC LICENSE") == "LGPL"
    assert github_api._gnu_variant_from_text("GNU AFFERO GENERAL PUBLIC LICENSE") == "AGPL"
    assert github_api._gnu_variant_from_text("MIT License") == ""


def test_gnu_variant_from_text_ignores_agpl_mention_in_gplv3_body() -> None:
    # GPLv3's own section 13 references "the GNU Affero General Public
    # License" as a compatibility clause -- a whole-document search would
    # wrongly call this AGPL. Real repro: ubeast/dbricks_utils.
    text = "GNU GENERAL PUBLIC LICENSE\nVersion 3" + ("x" * 500) + "13. Use with the GNU Affero General Public License."
    assert github_api._gnu_variant_from_text(text) == "GPL"


def test_detect_license_returns_spdx_id_without_extra_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a: object, **k: object) -> str:
        raise AssertionError("should not fetch license content when spdx_id is present")

    monkeypatch.setattr(github_api, "_fetch_license_text", _boom)
    raw = {"license": {"spdx_id": "MIT"}}
    assert github_api._detect_license(raw, "octocat/widget", headers={}) == "MIT"


def test_detect_license_falls_back_to_gnu_text_on_noassertion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        github_api, "_fetch_license_text", lambda full_name, headers: "GNU GENERAL PUBLIC LICENSE\nVersion 3"
    )
    raw = {"license": {"spdx_id": "NOASSERTION", "name": "Other"}}
    assert github_api._detect_license(raw, "octocat/widget", headers={}) == "GPL"


def test_detect_license_keeps_noassertion_when_text_is_not_gnu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_api, "_fetch_license_text", lambda full_name, headers: "Some custom license")
    raw = {"license": {"spdx_id": "NOASSERTION", "name": "Other"}}
    assert github_api._detect_license(raw, "octocat/widget", headers={}) == "NOASSERTION"


def test_detect_license_keeps_noassertion_when_no_license_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_api, "_fetch_license_text", lambda full_name, headers: "")
    raw = {"license": {"spdx_id": "NOASSERTION"}}
    assert github_api._detect_license(raw, "octocat/widget", headers={}) == "NOASSERTION"


def test_fetch_repos_requires_token_or_owner() -> None:
    with pytest.raises(github_api.ApiError):
        github_api.fetch_repos(token=None, owner=None)
