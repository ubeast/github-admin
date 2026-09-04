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
    other fields (README, license, contributors) isn't flagged, since an
    archived repo won't be improved and a fork inherits the upstream's docs.
    """
    issues: list[str] = []
    if repo.archived:
        return RepoHealth(repo=repo, issues=issues)

    if not repo.has_readme:
        issues.append("no README")
    if not repo.license:
        issues.append("no license")
    if repo.contributors is not None and repo.contributors <= 1 and not repo.is_fork:
        issues.append("no external contributors")
    if not repo.description:
        issues.append("no description")
    if not repo.topics:
        issues.append("no topics")
    if _is_stale(repo.pushed, stale_days, today or date.today()):
        issues.append(f"stale (no push in {stale_days}+ days)")

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
