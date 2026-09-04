"""GitHub API client: fetch every repo the token can see, with health-check fields.

Standard-library only (``urllib``) -- no HTTP client dependency. Adapted from
the ``fetch_github`` logic in ``one-file-tools/tools/repo-inventory/repo_inventory.py``,
narrowed to GitHub only and to the fields this tool's health checks need.
Unlike the source script (where the analogous fields are opt-in via
``--full``), those fields are always fetched here -- they're the point of
this tool.

Speed tradeoff: three extra requests per repo beyond the single list-endpoint
call -- one root-directory listing (``_root_listing``, which answers README /
CLAUDE.md / src-layout / tests / .gitignore / CI-config in a single request
rather than one request per item), one branch-protection check, and one
contributor count. For ~50 repos that's ~150 requests, comfortably inside
GitHub's authenticated rate limit (5000/hr) but noticeably slower than a
plain list.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = ["RepoInfo", "ApiError", "fetch_repos", "resolve_token"]

GITHUB_API = "https://api.github.com"
USER_AGENT = "github-admin/0.1 (+https://github.com/ubeast/github-admin)"


class ApiError(RuntimeError):
    """A non-retryable API failure with a human-readable message."""


@dataclass(frozen=True)
class RepoInfo:
    """One GitHub repo, normalised to the fields health checks need.

    ``license`` is ``""`` when no license is detected. ``contributors`` and
    ``branch_protected`` are ``None`` only if the value could not be
    determined (e.g. an empty repo with no commits yet, or a protection
    check the token lacks permission to read) -- distinct from ``False``,
    which means checked and confirmed missing/unprotected.
    """

    owner: str
    name: str
    full_name: str
    description: str
    visibility: str
    is_fork: bool
    archived: bool
    license: str
    has_readme: bool
    has_claude_md: bool
    has_src_layout: bool
    has_tests_dir: bool
    has_gitignore: bool
    has_ci_config: bool
    has_pyproject: bool
    branch_protected: bool | None
    contributors: int | None
    topics: list[str] = field(default_factory=list)
    language: str = ""
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    default_branch: str = ""
    created: str = ""
    updated: str = ""
    pushed: str = ""
    url: str = ""


def resolve_token(token_env: str = "GITHUB_TOKEN") -> str | None:
    """Find a GitHub token: ``token_env`` first, then ``gh auth token`` if the
    ``gh`` CLI is installed and logged in. Returns ``None`` if neither works.
    """
    import os

    token = os.environ.get(token_env)
    if token:
        return token

    import shutil
    import subprocess

    if not shutil.which("gh"):
        return None
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    token = result.stdout.strip()
    return token or None


def _headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request(url: str, headers: dict[str, str], *, timeout: float = 30.0) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- fixed https host
            body = resp.read()
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, hdrs, body
    except urllib.error.HTTPError as exc:
        body = exc.read()
        hdrs = {k.lower(): v for k, v in (exc.headers or {}).items()}
        return exc.code, hdrs, body
    except urllib.error.URLError as exc:
        raise ApiError(f"network error requesting {url}: {exc.reason}") from exc


def _rate_limit_pause(hdrs: dict[str, str]) -> float:
    retry_after = hdrs.get("retry-after")
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), 60.0)
    reset = hdrs.get("x-ratelimit-reset")
    if reset and reset.isdigit():
        return min(max(float(reset) - time.time(), 1.0), 60.0)
    return 5.0


def _is_rate_limited(status: int, hdrs: dict[str, str], body: bytes) -> bool:
    if status == 429:
        return True
    if hdrs.get("x-ratelimit-remaining") == "0":
        return True
    return b"rate limit" in body.lower() or b"secondary rate" in body.lower()


def _short_body(body: bytes) -> str:
    text = body.decode("utf-8", "replace").strip().replace("\n", " ")
    return (text[:200] + "...") if len(text) > 200 else text


def _get_json(url: str, headers: dict[str, str], *, retries: int = 1) -> tuple[Any, dict[str, str]]:
    """GET a JSON endpoint, retrying once on a rate-limit response."""
    attempt = 0
    while True:
        status, hdrs, body = _request(url, headers)
        if status == 200:
            return json.loads(body or b"null"), hdrs
        if status == 204:
            return None, hdrs
        if status in (403, 429) and _is_rate_limited(status, hdrs, body):
            if attempt < retries:
                wait = _rate_limit_pause(hdrs)
                print(f"  rate-limited, sleeping {wait:.0f}s then retrying...", file=sys.stderr)
                time.sleep(wait)
                attempt += 1
                continue
            raise ApiError("rate limit exceeded and retry did not help -- wait a while and try again")
        if status in (401, 403):
            raise ApiError(f"{status} from {url} -- check the token value and its scopes ({_short_body(body)})")
        if status == 404:
            raise ApiError(f"404 from {url} -- not found, or the token can't see it")
        raise ApiError(f"{status} from {url}: {_short_body(body)}")


def _parse_link_header(value: str | None) -> dict[str, str]:
    """Parse an RFC 5988 ``Link`` header into ``{rel: url}``."""
    out: dict[str, str] = {}
    if not value:
        return out
    for part in value.split(","):
        segs = part.split(";")
        if len(segs) < 2:
            continue
        link = segs[0].strip().lstrip("<").rstrip(">")
        for attr in segs[1:]:
            attr = attr.strip()
            if attr.startswith("rel="):
                out[attr[4:].strip().strip('"')] = link
    return out


def _last_page_from_link(value: str | None) -> int | None:
    links = _parse_link_header(value)
    last = links.get("last")
    if not last:
        return None
    query = urllib.parse.urlparse(last).query
    pages = urllib.parse.parse_qs(query).get("page")
    return int(pages[0]) if pages and pages[0].isdigit() else None


def _paginate(url: str, headers: dict[str, str]) -> list[Any]:
    items: list[Any] = []
    while url:
        data, hdrs = _get_json(url, headers)
        if isinstance(data, list):
            items.extend(data)
        elif data is not None:
            items.append(data)
        url = _parse_link_header(hdrs.get("link")).get("next", "")
    return items


def _date(value: Any) -> str:
    """Truncate an ISO 8601 timestamp to its ``YYYY-MM-DD`` date part."""
    if not value or not isinstance(value, str):
        return ""
    return value[:10] if len(value) >= 10 and value[4] == "-" else value


def _list_url(owner: str | None) -> str:
    if owner:
        return f"{GITHUB_API}/users/{urllib.parse.quote(owner)}/repos?per_page=100&sort=pushed"
    return (
        f"{GITHUB_API}/user/repos?per_page=100&sort=pushed"
        "&affiliation=owner,collaborator,organization_member"
    )


def _contributor_count(full_name: str, headers: dict[str, str]) -> int | None:
    url = f"{GITHUB_API}/repos/{full_name}/contributors?per_page=1&anon=1"
    try:
        data, hdrs = _get_json(url, headers)
    except ApiError:
        return None
    last = _last_page_from_link(hdrs.get("link"))
    if last is not None:
        return last
    return len(data) if isinstance(data, list) else 0


def _branch_protection(full_name: str, branch: str, headers: dict[str, str]) -> bool | None:
    """Whether ``branch`` can't be force-pushed to or deleted.

    "Protected" here specifically means: branch protection is enabled, and
    both force pushes and branch deletion are disallowed. Deliberately does
    NOT require PR review counts or status checks -- those make sense for a
    team workflow but not for solo work, and this tool covers both. The
    force-push/deletion guard is the one thing worth enforcing regardless
    of team size: it's the difference between "an accident can rewrite or
    delete history" and "it can't."

    Returns ``None`` (unknown, not "unprotected") if the check itself
    fails for a reason other than "no protection configured". In practice
    the common case is GitHub's branch-protection API being a paid-plan
    feature for *private* repos -- it 403s with "Upgrade to GitHub Pro or
    make this repository public" regardless of the token's permissions, so
    most private repos on a free plan will read as unknown here, not
    unprotected. Public repos get a real 404/200 answer either way.
    """
    if not branch:
        return None
    status, _, body = _request(
        f"{GITHUB_API}/repos/{full_name}/branches/{urllib.parse.quote(branch)}/protection", headers
    )
    if status == 404:
        return False
    if status != 200:
        return None
    try:
        data = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    force_push_allowed = bool((data.get("allow_force_pushes") or {}).get("enabled"))
    deletion_allowed = bool((data.get("allow_deletions") or {}).get("enabled"))
    return not force_push_allowed and not deletion_allowed


def _root_listing(full_name: str, headers: dict[str, str]) -> tuple[set[str], set[str]]:
    """Return ``(lowercased file names, lowercased dir names)`` at repo root.

    One call answers several structural checks at once (README, CLAUDE.md,
    src/ layout, tests/, .gitignore, CI config) instead of one dedicated
    call per item. Trade-off: this is a plain root-directory listing, not
    GitHub's smarter ``/readme`` endpoint, so it won't find a README that
    lives outside the repo root or resolve symlinks -- an edge case rare
    enough not to be worth a second call.
    """
    try:
        data, _ = _get_json(f"{GITHUB_API}/repos/{full_name}/contents", headers)
    except ApiError:
        return set(), set()
    if not isinstance(data, list):
        return set(), set()
    files = {e["name"].lower() for e in data if e.get("type") == "file" and "name" in e}
    dirs = {e["name"].lower() for e in data if e.get("type") == "dir" and "name" in e}
    return files, dirs


def _to_repo_info(raw: dict[str, Any], headers: dict[str, str]) -> RepoInfo:
    lic = raw.get("license") or {}
    full_name = raw.get("full_name") or f"{(raw.get('owner') or {}).get('login', '')}/{raw.get('name', '')}"
    files, dirs = _root_listing(full_name, headers)
    return RepoInfo(
        owner=(raw.get("owner") or {}).get("login", ""),
        name=raw.get("name", ""),
        full_name=full_name,
        description=raw.get("description") or "",
        visibility=raw.get("visibility") or ("private" if raw.get("private") else "public"),
        is_fork=bool(raw.get("fork")),
        archived=bool(raw.get("archived")),
        license=lic.get("spdx_id") or lic.get("name") or "",
        has_readme=any(f.startswith("readme") for f in files),
        has_claude_md="claude.md" in files,
        has_src_layout="src" in dirs,
        has_tests_dir="tests" in dirs or "test" in dirs,
        has_gitignore=".gitignore" in files,
        has_ci_config=".github" in dirs,
        has_pyproject="pyproject.toml" in files,
        branch_protected=_branch_protection(full_name, raw.get("default_branch") or "", headers),
        contributors=_contributor_count(full_name, headers),
        topics=list(raw.get("topics") or []),
        language=raw.get("language") or "",
        stars=int(raw.get("stargazers_count") or 0),
        forks=int(raw.get("forks_count") or 0),
        open_issues=int(raw.get("open_issues_count") or 0),
        default_branch=raw.get("default_branch") or "",
        created=_date(raw.get("created_at")),
        updated=_date(raw.get("updated_at")),
        pushed=_date(raw.get("pushed_at")),
        url=raw.get("html_url") or "",
    )


def fetch_repos(
    *,
    token: str | None,
    owner: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[RepoInfo]:
    """Fetch every repo the token can see (or ``owner``'s public repos).

    ``owner`` None -> the token owner's repos, including orgs they belong to
    (GitHub's ``affiliation=owner,collaborator,organization_member`` covers
    both personal and org repos in one call, so no separate per-org fetch is
    needed).
    """
    headers = _headers(token)
    if not token and not owner:
        raise ApiError("no token available -- set GITHUB_TOKEN or run `gh auth login`")

    say = progress or (lambda _msg: None)
    raws = _paginate(_list_url(owner), headers)
    records: list[RepoInfo] = []
    for raw in raws:
        name = raw.get("full_name") or raw.get("name", "?")
        say(f"  {name}")
        records.append(_to_repo_info(raw, headers))
    return records
