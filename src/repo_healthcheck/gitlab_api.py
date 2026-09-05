"""GitLab API client: fetch every project the token can see, with health-check fields.

Standard-library only (``urllib``), same convention as ``github_api.py``.
Ported from the ``fetch_gitlab`` logic in
``one-file-tools/tools/repo-inventory/repo_inventory.py`` -- that script's
GitLab support already covered the base listing fields (name, owner,
description, license, topics, stars, forks, contributors, archived, pushed,
README presence) and is reused here close to as-is. The structural checks
(CLAUDE.md / .gitignore / tests / CI config / pyproject) and branch
protection are new: the source script never built GitLab equivalents of
those (they're specific to this tool, not a general-purpose inventory), so
they're modelled here on ``github_api.py``'s versions using GitLab's
corresponding endpoints (``repository/tree`` and ``protected_branches``).

Every function returns the same ``RepoInfo`` shape ``github_api.py`` does
(``platform="gitlab"``) -- ``health.py`` and the renderers don't need to
know which platform a repo came from.

Two known simplifications, both matching the source script's scope rather
than expanding it speculatively:
  * ``owner`` with no value lists projects you're a *member* of; a specific
    GitLab *group* (as opposed to a user) isn't a supported target -- GitLab
    exposes those via a separate ``/groups/:id/projects`` endpoint the
    source script never added.
  * ``language`` is always blank -- GitLab's project list endpoint doesn't
    include it; getting it needs a separate ``/languages`` call per project,
    which the source script gated behind ``--full`` and isn't worth adding
    here for one column.

Speed tradeoff: same shape as ``github_api.py`` -- one root-tree listing,
one branch-protection check, and one contributor count per project beyond
the list call.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from repo_healthcheck.github_api import RepoInfo

__all__ = ["ApiError", "fetch_repos", "resolve_token", "GITLAB_DEFAULT_URL"]

GITLAB_DEFAULT_URL = "https://gitlab.com"
USER_AGENT = "repo-healthcheck/0.1 (+https://github.com/ubeast/repo-healthcheck)"


class ApiError(RuntimeError):
    """A non-retryable API failure with a human-readable message."""


def resolve_token(token_env: str = "GITLAB_TOKEN") -> str | None:
    """Find a GitLab token in ``token_env``. Returns ``None`` if unset.

    Unlike ``github_api.resolve_token``, there's no CLI-fallback step here --
    the source script this was adapted from only ever read ``GITLAB_TOKEN``
    directly (there's no GitLab CLI as ubiquitous as ``gh`` to fall back to),
    so that's preserved rather than guessing at an unverified equivalent.
    """
    return os.environ.get(token_env) or None


def _headers(token: str | None) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["PRIVATE-TOKEN"] = token
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


def _is_rate_limited(status: int, hdrs: dict[str, str]) -> bool:
    return status == 429 or hdrs.get("ratelimit-remaining") == "0"


def _rate_limit_pause(hdrs: dict[str, str]) -> float:
    retry_after = hdrs.get("retry-after")
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), 60.0)
    return 5.0


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
        if status == 429 or _is_rate_limited(status, hdrs):
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


def _paginate(url: str, headers: dict[str, str]) -> list[Any]:
    """Yield every item across a GitLab list endpoint's pages.

    GitLab paginates via an ``X-Next-Page`` response header (a page number,
    or empty on the last page) rather than GitHub's RFC 5988 ``Link``
    header, so this doesn't share ``github_api._paginate``.
    """
    items: list[Any] = []
    page = 1
    while page:
        sep = "&" if "?" in url else "?"
        data, hdrs = _get_json(f"{url}{sep}per_page=100&page={page}", headers)
        if isinstance(data, list):
            items.extend(data)
        elif data is not None:
            items.append(data)
        nxt = hdrs.get("x-next-page", "").strip()
        page = int(nxt) if nxt.isdigit() else 0
    return items


def _date(value: Any) -> str:
    """Truncate an ISO 8601 timestamp to its ``YYYY-MM-DD`` date part."""
    if not value or not isinstance(value, str):
        return ""
    return value[:10] if len(value) >= 10 and value[4] == "-" else value


def _api(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/v4"


def _list_url(base_url: str, owner: str | None) -> str:
    api = _api(base_url)
    common = "license=true&statistics=false&order_by=last_activity_at"
    if owner:
        return f"{api}/users/{urllib.parse.quote(owner)}/projects?{common}"
    return f"{api}/projects?membership=true&{common}"


def _contributor_count(base_url: str, project_id: int, headers: dict[str, str]) -> int | None:
    url = f"{_api(base_url)}/projects/{project_id}/repository/contributors?per_page=1"
    try:
        _, hdrs = _get_json(url, headers)
    except ApiError:
        return None
    total = hdrs.get("x-total")
    return int(total) if total and total.isdigit() else None


def _root_listing(base_url: str, project_id: int, ref: str, headers: dict[str, str]) -> tuple[set[str], set[str]]:
    """Return ``(lowercased file names, lowercased dir names)`` at repo root.

    GitLab's ``repository/tree`` (non-recursive, the default) lists just the
    root level for a given ``ref`` -- the direct equivalent of
    ``github_api._root_listing``'s contents-API call. Returns empty sets on
    any error, including an empty repo with no commits yet on ``ref``
    (a 404 from GitLab in that case).
    """
    if not ref:
        return set(), set()
    url = f"{_api(base_url)}/projects/{project_id}/repository/tree?ref={urllib.parse.quote(ref)}&per_page=100"
    try:
        data, _ = _get_json(url, headers)
    except ApiError:
        return set(), set()
    if not isinstance(data, list):
        return set(), set()
    files = {e["name"].lower() for e in data if e.get("type") == "blob" and "name" in e}
    dirs = {e["name"].lower() for e in data if e.get("type") == "tree" and "name" in e}
    return files, dirs


def _branch_protection(base_url: str, project_id: int, branch: str, headers: dict[str, str]) -> bool | None:
    """Whether ``branch`` can't be force-pushed to or deleted.

    Mirrors ``github_api._branch_protection``'s definition, adapted to how
    GitLab actually models it: a protected branch can't be deleted by
    anyone below the configured access level without unprotecting it first
    -- there's no separate "allow deletions" toggle the way GitHub has one,
    so a 200 response already covers the deletion half. The remaining
    question is force-push, which GitLab reports directly as
    ``allow_force_push``.

    Returns ``None`` (unknown) only if the check itself fails for a reason
    other than "no protection configured" -- e.g. the token lacks
    permission to read protected-branch settings on this project.
    """
    if not branch:
        return None
    status, _, body = _request(
        f"{_api(base_url)}/projects/{project_id}/protected_branches/{urllib.parse.quote(branch, safe='')}",
        headers,
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
    return not bool(data.get("allow_force_push", False))


def _license_file_name(files: set[str]) -> str | None:
    return next((f for f in files if f == "license" or f.startswith("license.")), None)


def _read_raw_file(base_url: str, project_id: int, filename: str, ref: str, headers: dict[str, str]) -> str:
    """Fetch one root-level file's raw text content.

    ``filename`` must be exactly cased -- GitLab's raw-file endpoint is a
    real git blob path lookup, unlike GitHub's dedicated ``/license``
    endpoint which resolves case-insensitively. See
    ``_find_root_file_exact_name`` for recovering the real casing from a
    lowercased root listing.
    """
    url = (
        f"{_api(base_url)}/projects/{project_id}/repository/files/"
        f"{urllib.parse.quote(filename, safe='')}/raw?ref={urllib.parse.quote(ref)}"
    )
    status, _, body = _request(url, headers)
    if status != 200:
        return ""
    return body.decode("utf-8", "replace")


def _find_root_file_exact_name(
    base_url: str, project_id: int, ref: str, prefix: str, headers: dict[str, str]
) -> str | None:
    """Recover a root-level file's real-cased name from its lowercase prefix.

    ``_root_listing`` lowercases names for the boolean structural checks,
    which loses the casing needed to actually fetch one file's content (e.g.
    ``LICENSE`` vs ``License.md``). Only called in the rare license-fallback
    path, so the extra tree request doesn't cost anything for the common case.
    """
    if not ref:
        return None
    url = f"{_api(base_url)}/projects/{project_id}/repository/tree?ref={urllib.parse.quote(ref)}&per_page=100"
    try:
        data, _ = _get_json(url, headers)
    except ApiError:
        return None
    if not isinstance(data, list):
        return None
    for entry in data:
        name = entry.get("name", "")
        if entry.get("type") == "blob" and name.lower().startswith(prefix):
            return name
    return None


def _gnu_variant_from_text(text: str) -> str:
    """Identify a GNU license family from its own declared name in the file text.

    Same rationale and same 300-character cap as
    ``github_api._gnu_variant_from_text`` -- GPL's own text (section 13)
    references "the GNU Affero General Public License" in a compatibility
    clause, so scanning the whole file would misidentify plain GPL as AGPL.
    The title always appears in the first line or two.
    """
    upper = text[:300].upper()
    if "GNU AFFERO GENERAL PUBLIC LICENSE" in upper:
        return "AGPL"
    if "GNU LESSER GENERAL PUBLIC LICENSE" in upper:
        return "LGPL"
    if "GNU GENERAL PUBLIC LICENSE" in upper:
        return "GPL"
    if "GNU FREE DOCUMENTATION LICENSE" in upper:
        return "GFDL"
    return ""


def _detect_license(
    proj: dict[str, Any], base_url: str, project_id: Any, ref: str, files: set[str], headers: dict[str, str]
) -> str:
    lic = proj.get("license") or {}
    detected = lic.get("nickname") or lic.get("name") or lic.get("key") or ""
    if detected or not isinstance(project_id, int):
        return detected
    if not _license_file_name(files):
        return detected
    exact_name = _find_root_file_exact_name(base_url, project_id, ref, "license", headers)
    if not exact_name:
        return detected
    return _gnu_variant_from_text(_read_raw_file(base_url, project_id, exact_name, ref, headers)) or detected


def _to_repo_info(base_url: str, proj: dict[str, Any], headers: dict[str, str]) -> RepoInfo:
    namespace = proj.get("namespace") or {}
    owner = namespace.get("full_path") or namespace.get("path") or ""
    name = proj.get("path") or proj.get("name") or ""
    full_name = f"{owner}/{name}" if owner else name
    topics = proj.get("topics")
    if not topics:
        topics = proj.get("tag_list") or []
    default_branch = proj.get("default_branch") or ""
    project_id = proj.get("id")

    files: set[str] = set()
    dirs: set[str] = set()
    contributors: int | None = None
    protected: bool | None = None
    if isinstance(project_id, int):
        files, dirs = _root_listing(base_url, project_id, default_branch, headers)
        contributors = _contributor_count(base_url, project_id, headers)
        protected = _branch_protection(base_url, project_id, default_branch, headers)

    return RepoInfo(
        owner=owner,
        name=name,
        full_name=full_name,
        description=proj.get("description") or "",
        visibility=proj.get("visibility") or "",
        is_fork=bool(proj.get("forked_from_project")),
        archived=bool(proj.get("archived")),
        license=_detect_license(proj, base_url, project_id, default_branch, files, headers),
        has_readme=bool(proj.get("readme_url")) or any(f.startswith("readme") for f in files),
        has_claude_md="claude.md" in files,
        has_src_layout="src" in dirs,
        has_tests_dir="tests" in dirs or "test" in dirs,
        has_gitignore=".gitignore" in files,
        has_ci_config=".gitlab-ci.yml" in files,
        has_pyproject="pyproject.toml" in files,
        branch_protected=protected,
        contributors=contributors,
        platform="gitlab",
        topics=list(topics),
        language="",
        stars=int(proj.get("star_count") or 0),
        forks=int(proj.get("forks_count") or 0),
        open_issues=int(proj.get("open_issues_count") or 0),
        default_branch=default_branch,
        created=_date(proj.get("created_at")),
        updated=_date(proj.get("last_activity_at")),
        pushed=_date(proj.get("last_activity_at")),
        url=proj.get("web_url") or "",
    )


def fetch_repos(
    *,
    token: str | None,
    owner: str | None = None,
    base_url: str = GITLAB_DEFAULT_URL,
    progress: Callable[[str], None] | None = None,
) -> list[RepoInfo]:
    """Fetch every GitLab project the token can see (or ``owner``'s public ones).

    ``owner`` None -> every project you're a member of (token required).
    ``owner`` set -> that user's public projects (works tokenless, subject
    to GitLab's unauthenticated rate limit).
    """
    headers = _headers(token)
    if not token and not owner:
        raise ApiError("no GitLab token available -- set GITLAB_TOKEN, or pass --gitlab-owner for public projects")

    say = progress or (lambda _msg: None)
    raws = _paginate(_list_url(base_url, owner), headers)
    records: list[RepoInfo] = []
    for raw in raws:
        namespace = raw.get("namespace") or {}
        label = f"{namespace.get('full_path', '')}/{raw.get('path', raw.get('name', '?'))}"
        say(f"  {label}")
        records.append(_to_repo_info(base_url, raw, headers))
    return records
