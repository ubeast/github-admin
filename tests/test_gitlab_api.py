from __future__ import annotations

import pytest

from repo_healthcheck import gitlab_api


def test_resolve_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-xxx")
    assert gitlab_api.resolve_token() == "glpat-xxx"


def test_resolve_token_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    assert gitlab_api.resolve_token() is None


def test_date_truncates_iso_timestamp() -> None:
    assert gitlab_api._date("2024-06-07T08:09:10.000Z") == "2024-06-07"
    assert gitlab_api._date("") == ""
    assert gitlab_api._date(None) == ""


def test_root_listing_splits_files_and_dirs(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        {"name": "README.md", "type": "blob"},
        {"name": "CLAUDE.md", "type": "blob"},
        {"name": ".gitignore", "type": "blob"},
        {"name": ".gitlab-ci.yml", "type": "blob"},
        {"name": "pyproject.toml", "type": "blob"},
        {"name": "src", "type": "tree"},
        {"name": "tests", "type": "tree"},
    ]
    monkeypatch.setattr(gitlab_api, "_get_json", lambda url, headers: (entries, {}))
    files, dirs = gitlab_api._root_listing("https://gitlab.com", 1, "main", headers={})
    assert files == {"readme.md", "claude.md", ".gitignore", ".gitlab-ci.yml", "pyproject.toml"}
    assert dirs == {"src", "tests"}


def test_root_listing_empty_without_ref() -> None:
    files, dirs = gitlab_api._root_listing("https://gitlab.com", 1, "", headers={})
    assert files == set()
    assert dirs == set()


def test_root_listing_empty_on_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(url: str, headers: dict[str, str]) -> None:
        raise gitlab_api.ApiError("404")

    monkeypatch.setattr(gitlab_api, "_get_json", _raise)
    files, dirs = gitlab_api._root_listing("https://gitlab.com", 1, "main", headers={})
    assert files == set()
    assert dirs == set()


def test_branch_protection_false_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gitlab_api, "_request", lambda url, headers: (404, {}, b""))
    assert gitlab_api._branch_protection("https://gitlab.com", 1, "main", headers={}) is False


def test_branch_protection_unknown_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gitlab_api, "_request", lambda url, headers: (403, {}, b""))
    assert gitlab_api._branch_protection("https://gitlab.com", 1, "main", headers={}) is None


def test_branch_protection_true_when_force_push_disallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b'{"allow_force_push": false}'
    monkeypatch.setattr(gitlab_api, "_request", lambda url, headers: (200, {}, body))
    assert gitlab_api._branch_protection("https://gitlab.com", 1, "main", headers={}) is True


def test_branch_protection_false_when_force_push_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b'{"allow_force_push": true}'
    monkeypatch.setattr(gitlab_api, "_request", lambda url, headers: (200, {}, body))
    assert gitlab_api._branch_protection("https://gitlab.com", 1, "main", headers={}) is False


def test_branch_protection_none_without_branch_name() -> None:
    assert gitlab_api._branch_protection("https://gitlab.com", 1, "", headers={}) is None


def test_to_repo_info_maps_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gitlab_api,
        "_root_listing",
        lambda base_url, project_id, ref, headers: ({"claude.md", "pyproject.toml"}, {"src"}),
    )
    monkeypatch.setattr(gitlab_api, "_contributor_count", lambda base_url, project_id, headers: 4)
    monkeypatch.setattr(gitlab_api, "_branch_protection", lambda base_url, project_id, branch, headers: True)

    raw = {
        "id": 42,
        "path": "widget",
        "name": "Widget",
        "namespace": {"full_path": "myteam"},
        "description": "a widget",
        "visibility": "public",
        "forked_from_project": None,
        "archived": False,
        "star_count": 5,
        "forks_count": 1,
        "open_issues_count": 2,
        "topics": ["cli"],
        "license": {"nickname": "MIT License"},
        "default_branch": "main",
        "created_at": "2020-01-02T03:04:05.000Z",
        "last_activity_at": "2024-06-07T08:09:10.000Z",
        "web_url": "https://gitlab.com/myteam/widget",
        "readme_url": "https://gitlab.com/myteam/widget/-/blob/main/README.md",
    }
    rec = gitlab_api._to_repo_info("https://gitlab.com", raw, headers={})
    assert rec.platform == "gitlab"
    assert rec.owner == "myteam"
    assert rec.full_name == "myteam/widget"
    assert rec.license == "MIT License"
    assert rec.has_readme is True
    assert rec.has_claude_md is True
    assert rec.has_src_layout is True
    assert rec.has_tests_dir is False
    assert rec.has_ci_config is False
    assert rec.has_pyproject is True
    assert rec.branch_protected is True
    assert rec.contributors == 4
    assert rec.stars == 5
    assert rec.created == "2020-01-02"
    assert rec.pushed == "2024-06-07"


def test_to_repo_info_skips_extra_calls_without_project_id() -> None:
    raw = {"path": "widget", "namespace": {"full_path": "myteam"}, "default_branch": "main"}
    rec = gitlab_api._to_repo_info("https://gitlab.com", raw, headers={})
    assert rec.contributors is None
    assert rec.branch_protected is None
    assert rec.has_claude_md is False


def test_gnu_variant_from_text_identifies_gpl_family() -> None:
    assert gitlab_api._gnu_variant_from_text("GNU GENERAL PUBLIC LICENSE") == "GPL"
    assert gitlab_api._gnu_variant_from_text("GNU LESSER GENERAL PUBLIC LICENSE") == "LGPL"
    assert gitlab_api._gnu_variant_from_text("Apache License 2.0") == ""


def test_detect_license_returns_detected_without_extra_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a: object, **k: object) -> str:
        raise AssertionError("should not fetch file content when a license is already detected")

    monkeypatch.setattr(gitlab_api, "_read_raw_file", _boom)
    proj = {"license": {"nickname": "MIT License"}}
    assert gitlab_api._detect_license(proj, "https://gitlab.com", 1, "main", {"license"}, headers={}) == "MIT License"


def test_detect_license_falls_back_to_gnu_text_when_undetected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gitlab_api, "_find_root_file_exact_name", lambda base_url, pid, ref, prefix, headers: "LICENSE"
    )
    monkeypatch.setattr(
        gitlab_api, "_read_raw_file", lambda base_url, pid, filename, ref, headers: "GNU GENERAL PUBLIC LICENSE"
    )
    proj = {"license": None}
    assert gitlab_api._detect_license(proj, "https://gitlab.com", 1, "main", {"license"}, headers={}) == "GPL"


def test_detect_license_skips_without_project_id() -> None:
    proj = {"license": None}
    assert gitlab_api._detect_license(proj, "https://gitlab.com", None, "main", {"license"}, headers={}) == ""


def test_detect_license_skips_without_license_file() -> None:
    proj = {"license": None}
    assert gitlab_api._detect_license(proj, "https://gitlab.com", 1, "main", set(), headers={}) == ""


def test_find_root_file_exact_name_matches_case_insensitively(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [{"name": "LICENSE", "type": "blob"}, {"name": "src", "type": "tree"}]
    monkeypatch.setattr(gitlab_api, "_get_json", lambda url, headers: (entries, {}))
    assert gitlab_api._find_root_file_exact_name("https://gitlab.com", 1, "main", "license", headers={}) == "LICENSE"


def test_fetch_repos_requires_token_or_owner() -> None:
    with pytest.raises(gitlab_api.ApiError):
        gitlab_api.fetch_repos(token=None, owner=None)
