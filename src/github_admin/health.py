"""Turn a raw ``RepoInfo`` into a health check: what's missing, at a glance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from github_admin.github_api import RepoInfo

__all__ = ["RepoHealth", "check", "DEFAULT_STALE_DAYS"]

# A repo with no pushes in this many days is flagged "stale". No universal
# right answer here -- 180 days is a starting guess (roughly two quarters of
# inactivity); override with --stale-days if it doesn't match your cadence.
DEFAULT_STALE_DAYS = 180


@dataclass(frozen=True)
class RepoHealth:
    """A repo plus the list of issues found in it (empty list = healthy)."""

    repo: RepoInfo
    issues: list[str]

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def is_healthy(self) -> bool:
        return not self.issues


def _is_stale(pushed: str, stale_days: int, today: date) -> bool:
    if not pushed:
        return False
    try:
        pushed_date = datetime.strptime(pushed, "%Y-%m-%d").date()
    except ValueError:
        return False
    return (today - pushed_date).days > stale_days


def check(repo: RepoInfo, *, stale_days: int = DEFAULT_STALE_DAYS, today: date | None = None) -> RepoHealth:
    """Evaluate one repo against the standard health checks.

    Archived and forked repos are informational only -- their emptiness in
    other fields (README, license, contributors, CI config) isn't flagged,
    since an archived repo won't be improved and a fork inherits the
    upstream's docs and workflows.
    """
    issues: list[str] = []
    if repo.archived:
        return RepoHealth(repo=repo, issues=issues)

    if not repo.has_readme:
        issues.append("no README")
    if not repo.has_claude_md:
        issues.append("no CLAUDE.md")
    if not repo.license:
        issues.append("no license")
    if repo.contributors is not None and repo.contributors <= 1 and not repo.is_fork:
        issues.append("no external contributors")
    if not repo.description:
        issues.append("no description")
    if not repo.topics:
        issues.append("no topics")
    if not repo.has_gitignore:
        issues.append("no .gitignore")
    if not repo.has_tests_dir:
        issues.append("no tests directory")
    # Forks are exempt, same reasoning as the contributors check above: you
    # didn't choose to set up CI for someone else's code, so its absence on
    # a fork isn't a signal about you.
    if not repo.has_ci_config and not repo.is_fork:
        issues.append("no CI config")
    if repo.language == "Python" and not repo.has_pyproject:
        issues.append("no pyproject.toml")
    if repo.branch_protected is False:
        issues.append("main branch not protected")
    if _is_stale(repo.pushed, stale_days, today or date.today()):
        issues.append(f"stale (no push in {stale_days}+ days)")

    # has_src_layout is deliberately NOT flagged here: it's a real, useful
    # signal (surfaced in the renderers), but "should this repo use a src/
    # layout" depends on project shape in a way the others don't -- a
    # single-file tool repo (see one-file-tools' own CLAUDE.md) correctly
    # skips it on purpose. Treat it as something to eyeball, not enforce.

    return RepoHealth(repo=repo, issues=issues)


def check_all(
    repos: list[RepoInfo], *, stale_days: int = DEFAULT_STALE_DAYS, today: date | None = None
) -> list[RepoHealth]:
    """Check every repo, sorted worst-first (most issues first) so nothing
    with problems gets buried below healthy repos.
    """
    day = today or date.today()
    results = [check(r, stale_days=stale_days, today=day) for r in repos]
    return sorted(results, key=lambda h: (-h.issue_count, h.repo.full_name.lower()))
