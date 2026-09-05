from __future__ import annotations

from repo_healthcheck import render_html
from repo_healthcheck.github_api import RepoInfo
from repo_healthcheck.health import RepoHealth


def _repo(**overrides: object) -> RepoInfo:
    defaults: dict[str, object] = dict(
        owner="octocat",
        name="widget",
        full_name="octocat/widget",
        description="a widget",
        visibility="public",
        is_fork=False,
        archived=False,
        license="",
        has_readme=False,
        has_claude_md=False,
        has_src_layout=False,
        has_tests_dir=False,
        has_gitignore=False,
        has_ci_config=False,
        has_pyproject=False,
        branch_protected=None,
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


def test_render_html_includes_repo_and_issues() -> None:
    r = _repo()
    result = RepoHealth(repo=r, issues=["no README", "no license"])
    out = render_html.render([result])
    # single-owner report: shown by short name in the link text, full name kept in its title attribute
    assert ">widget<" in out
    assert 'title="octocat/widget"' in out
    assert "no README" in out
    assert "<!doctype html>" in out


def test_render_html_shows_full_name_for_non_primary_owner() -> None:
    primary = RepoHealth(repo=_repo(owner="acme", full_name="acme/one", name="one"), issues=[])
    other = RepoHealth(repo=_repo(owner="acme", full_name="acme/two", name="two"), issues=[])
    outsider = RepoHealth(repo=_repo(owner="beta", full_name="beta/three", name="three"), issues=[])
    out = render_html.render([primary, other, outsider])
    assert ">beta/three<" in out
    assert ">one<" in out
    assert ">two<" in out
    assert ">acme/one<" not in out


def test_render_html_escapes_html_in_fields() -> None:
    r = _repo(description="<script>alert(1)</script>")
    result = RepoHealth(repo=r, issues=[])
    out = render_html.render([result])
    assert "<script>alert(1)</script>" not in out


def test_render_html_marks_healthy_repos_ok() -> None:
    r = _repo(has_readme=True, has_claude_md=True, license="MIT", topics=["cli"], description="x")
    result = RepoHealth(repo=r, issues=[])
    out = render_html.render([result])
    assert ">ok<" in out


def test_render_html_shows_unknown_branch_protection() -> None:
    r = _repo(branch_protected=None)
    result = RepoHealth(repo=r, issues=[])
    out = render_html.render([result])
    assert 'class="unknown">?<' in out
