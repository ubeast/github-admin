from __future__ import annotations

from repo_healthcheck import render_dashboard
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
        language="",
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


def test_render_includes_repo_name_and_doctype() -> None:
    r = _repo()
    result = RepoHealth(repo=r, issues=["no README", "no license"])
    out = render_dashboard.render([result])
    # single-owner report: shown by short name, full name kept in its title attribute
    assert ">widget<" in out
    assert 'title="octocat/widget"' in out
    assert "<!doctype html>" in out


def test_render_shows_full_name_only_for_non_primary_owner() -> None:
    primary = RepoHealth(repo=_repo(owner="acme", full_name="acme/one", name="one"), issues=[])
    other = RepoHealth(repo=_repo(owner="acme", full_name="acme/two", name="two"), issues=[])
    outsider = RepoHealth(repo=_repo(owner="beta", full_name="beta/three", name="three"), issues=[])
    out = render_dashboard.render([primary, other, outsider])
    assert ">beta/three<" in out
    assert ">one<" in out
    assert ">two<" in out
    assert ">acme/one<" not in out
    assert ">acme/two<" not in out


def test_render_escapes_html_in_fields() -> None:
    r = _repo(description="<script>alert(1)</script>")
    result = RepoHealth(repo=r, issues=[])
    out = render_dashboard.render([result])
    assert "<script>alert(1)</script>" not in out


def test_render_shows_tristate_badges_distinctly() -> None:
    protected_true = RepoHealth(repo=_repo(full_name="a/protected", branch_protected=True), issues=[])
    protected_false = RepoHealth(repo=_repo(full_name="b/unprotected", branch_protected=False), issues=[])
    protected_unknown = RepoHealth(repo=_repo(full_name="c/unknown", branch_protected=None), issues=[])
    out = render_dashboard.render([protected_true, protected_false, protected_unknown])
    assert 'class="badge-pill good">protected' in out
    assert 'class="badge-pill bad">not protected' in out
    assert 'class="badge-pill na">unknown' in out


def test_render_scope_reflects_actual_owners() -> None:
    a = RepoHealth(repo=_repo(full_name="acme/one", owner="acme"), issues=[])
    b = RepoHealth(repo=_repo(full_name="beta/two", owner="beta"), issues=[])
    out = render_dashboard.render([a, b])
    assert "acme" in out and "beta" in out


def test_render_handles_empty_results_without_crashing() -> None:
    out = render_dashboard.render([])
    assert "<!doctype html>" in out
    assert ">0<" in out  # repo count


def test_render_includes_fork_filter_markup_and_counts() -> None:
    forked = RepoHealth(repo=_repo(full_name="acme/fork", is_fork=True), issues=[])
    original = RepoHealth(repo=_repo(full_name="acme/original", is_fork=False), issues=[])
    out = render_dashboard.render([forked, original])
    assert 'data-fork="true"' in out
    assert 'data-fork="false"' in out
    assert 'id="forks-only-chip"' in out
    assert 'id="originals-only-chip"' in out
    assert 'data-fork-filter="forks"' in out
    assert 'data-fork-filter="originals"' in out


def test_render_includes_sort_data_attributes() -> None:
    r = _repo(forks=3, contributors=5)
    result = RepoHealth(repo=r, issues=[])
    out = render_dashboard.render([result])
    assert 'data-sort-forks="3"' in out
    assert 'data-sort-contributors="5"' in out
    assert 'data-sort-key="gaps"' in out
