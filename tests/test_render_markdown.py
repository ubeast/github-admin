from __future__ import annotations

from repo_healthcheck import render_markdown
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


def test_render_markdown_includes_repo_and_issues() -> None:
    r = _repo()
    result = RepoHealth(repo=r, issues=["no README", "no license"])
    out = render_markdown.render([result])
    assert out.startswith("# repo-healthcheck")
    # single-owner report: short name is the link label, full name kept in the link title
    assert "[widget](https://github.com/octocat/widget \"octocat/widget\")" in out
    assert "no README; no license" in out
    # a real Markdown table: header + alignment separator row
    assert "| repo | readme |" in out
    assert "| --- | :-: |" in out


def test_render_markdown_shows_full_name_for_non_primary_owner() -> None:
    primary = RepoHealth(repo=_repo(owner="acme", full_name="acme/one", name="one"), issues=[])
    other = RepoHealth(repo=_repo(owner="acme", full_name="acme/two", name="two"), issues=[])
    outsider = RepoHealth(repo=_repo(owner="beta", full_name="beta/three", name="three"), issues=[])
    out = render_markdown.render([primary, other, outsider])
    assert "[beta/three]" in out
    assert "[one]" in out
    assert "[two]" in out
    assert "[acme/one]" not in out


def test_render_markdown_escapes_pipes_in_issue_text() -> None:
    r = _repo()
    result = RepoHealth(repo=r, issues=["weird | issue"])
    out = render_markdown.render([result])
    assert r"weird \| issue" in out
    # the raw pipe must not leak through and split the cell
    assert "| weird | issue |" not in out


def test_render_markdown_marks_healthy_repos_ok() -> None:
    r = _repo(has_readme=True, has_claude_md=True, license="MIT", topics=["cli"], description="x")
    result = RepoHealth(repo=r, issues=[])
    out = render_markdown.render([result])
    assert "| ok |" in out


def test_render_markdown_shows_unknown_branch_protection() -> None:
    r = _repo(branch_protected=None)
    result = RepoHealth(repo=r, issues=[])
    out = render_markdown.render([result])
    lines = [ln for ln in out.splitlines() if ln.startswith("| [widget]")]
    assert len(lines) == 1
    # protected is the 4th data column -> 5th cell after the leading empty split
    assert lines[0].split("|")[4].strip() == "?"


def test_render_markdown_platform_and_archived_notes() -> None:
    gl = RepoHealth(repo=_repo(platform="gitlab", url="https://gitlab.com/octocat/widget"), issues=[])
    arch = RepoHealth(repo=_repo(name="old", full_name="octocat/old", archived=True), issues=[])
    out = render_markdown.render([gl, arch])
    assert "(gitlab)" in out
    assert "(archived)" in out
