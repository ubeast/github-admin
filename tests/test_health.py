from __future__ import annotations

from datetime import date

from github_admin import health
from github_admin.github_api import RepoInfo


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
        contributors=3,
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
    return RepoInfo(**defaults)  # type: ignore[arg-type]


def test_healthy_repo_has_no_issues() -> None:
    result = health.check(_repo(), today=date(2024, 2, 1))
    assert result.is_healthy
    assert result.issues == []


def test_flags_missing_readme() -> None:
    result = health.check(_repo(has_readme=False), today=date(2024, 2, 1))
    assert "no README" in result.issues


def test_flags_missing_claude_md() -> None:
    result = health.check(_repo(has_claude_md=False), today=date(2024, 2, 1))
    assert "no CLAUDE.md" in result.issues


def test_flags_missing_license() -> None:
    result = health.check(_repo(license=""), today=date(2024, 2, 1))
    assert "no license" in result.issues


def test_flags_no_external_contributors() -> None:
    result = health.check(_repo(contributors=1), today=date(2024, 2, 1))
    assert "no external contributors" in result.issues


def test_forks_are_not_flagged_for_contributors() -> None:
    result = health.check(_repo(contributors=1, is_fork=True), today=date(2024, 2, 1))
    assert "no external contributors" not in result.issues


def test_forks_are_not_flagged_for_missing_ci_config() -> None:
    result = health.check(_repo(has_ci_config=False, is_fork=True), today=date(2024, 2, 1))
    assert "no CI config" not in result.issues


def test_unknown_contributor_count_not_flagged() -> None:
    result = health.check(_repo(contributors=None), today=date(2024, 2, 1))
    assert "no external contributors" not in result.issues


def test_flags_missing_description_and_topics() -> None:
    result = health.check(_repo(description="", topics=[]), today=date(2024, 2, 1))
    assert "no description" in result.issues
    assert "no topics" in result.issues


def test_flags_missing_gitignore_tests_and_ci() -> None:
    result = health.check(
        _repo(has_gitignore=False, has_tests_dir=False, has_ci_config=False), today=date(2024, 2, 1)
    )
    assert "no .gitignore" in result.issues
    assert "no tests directory" in result.issues
    assert "no CI config" in result.issues


def test_flags_missing_pyproject_only_for_python() -> None:
    result = health.check(_repo(language="Python", has_pyproject=False), today=date(2024, 2, 1))
    assert "no pyproject.toml" in result.issues


def test_missing_pyproject_not_flagged_for_non_python() -> None:
    result = health.check(_repo(language="JavaScript", has_pyproject=False), today=date(2024, 2, 1))
    assert "no pyproject.toml" not in result.issues


def test_flags_unprotected_branch() -> None:
    result = health.check(_repo(branch_protected=False), today=date(2024, 2, 1))
    assert "main branch not protected" in result.issues


def test_unknown_branch_protection_not_flagged() -> None:
    result = health.check(_repo(branch_protected=None), today=date(2024, 2, 1))
    assert "main branch not protected" not in result.issues


def test_src_layout_never_flagged_as_issue() -> None:
    result = health.check(_repo(has_src_layout=False), today=date(2024, 2, 1))
    assert not any("src" in issue for issue in result.issues)


def test_flags_stale_repo() -> None:
    result = health.check(_repo(pushed="2023-01-01"), stale_days=180, today=date(2024, 2, 1))
    assert any(issue.startswith("stale") for issue in result.issues)


def test_recent_push_not_stale() -> None:
    result = health.check(_repo(pushed="2024-01-15"), stale_days=180, today=date(2024, 2, 1))
    assert not any(issue.startswith("stale") for issue in result.issues)


def test_archived_repo_has_no_issues_regardless() -> None:
    result = health.check(
        _repo(archived=True, has_readme=False, license="", description="", topics=[]),
        today=date(2024, 2, 1),
    )
    assert result.is_healthy


def test_check_all_sorts_worst_first() -> None:
    healthy = _repo(full_name="a/healthy")
    unhealthy = _repo(full_name="b/unhealthy", has_readme=False, license="")
    results = health.check_all([healthy, unhealthy], today=date(2024, 2, 1))
    assert results[0].repo.full_name == "b/unhealthy"
    assert results[1].repo.full_name == "a/healthy"
