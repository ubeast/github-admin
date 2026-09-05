# repo-healthcheck

A CLI that consolidates every GitHub repo you can see (and, with `--gitlab`,
your GitLab projects too) into one health-check view (README / CLAUDE.md /
branch protection / license / contributors / description / topics /
structure / staleness). See `README.md` for usage and the check list.

## Design decisions worth knowing

- **Read-only v1.** The tool only reads from the GitHub API right now; it
  does not write anything back. Bulk-fix actions (apply a license, add
  topics, etc.) are a deliberately deferred later iteration -- building the
  fix workflow before knowing, from real usage, what it needs to support
  risked designing it wrong and redoing it. The data layer
  (`github_api.py`) is already shaped to make adding that layer on top
  cheap: it returns plain typed records, decoupled from rendering.
- **`RepoInfo` (`github_api.py`) is the single source of truth.** Both
  renderers (`render_terminal.py`, `render_html.py`) and the health checker
  (`health.py`) consume the same records. Add a new health signal by adding
  a field to `RepoInfo` + a fetch step, then a check in `health.py` -- the
  renderers pick it up by iterating `RepoHealth.issues`, no per-renderer
  change needed for a new *issue type* (only for a new *column*).
- **Always fetches structural + protection data** (three extra requests per
  repo beyond the repo-list call: one root-directory listing, one
  branch-protection check, one contributor count). The source script this
  was adapted from (`one-file-tools/tools/repo-inventory/repo_inventory.py`)
  gates the analogous fields behind `--full` since it's a general-purpose
  inventory tool where most users don't need them. Here they're never
  optional -- they're exactly what the tool exists to check.
- **One root-directory listing answers several checks at once**
  (`_root_listing` in `github_api.py`) -- README, CLAUDE.md, src/ layout,
  tests/, .gitignore, CI config all come from a single `contents` API call
  instead of one call per item. Add a new "does this file/dir exist at
  root" check by reading from that same listing, not a new request.
- **`has_src_layout` is data, not an issue.** Every other structural check
  (`has_gitignore`, `has_tests_dir`, `has_ci_config`, ...) is wired into
  `health.py`'s issue list; src/ layout deliberately isn't, because whether
  a repo *should* have one depends on project shape (a real single-file
  tool repo, like this project's own source `one-file-tools`, correctly
  has none). It's surfaced as an informational column in `render_html.py`
  instead of being enforced.
- **License detection has one narrow, deliberately scoped fallback (2026-09,
  fixes issue #1).** GitHub's license detector reports `NOASSERTION` for
  some unmodified, standard-text GNU licenses -- confirmed on
  `ubeast/dbricks_utils`, whose `LICENSE` is the literal, unedited GPLv3
  text but which GitHub's API classifies as `NOASSERTION`/"Other". Since
  GNU licenses always state their own name in the title, `_detect_license`
  (`github_api.py`, `gitlab_api.py`) fetches the actual file text in that
  one case and checks for the GNU family name, resolving to `GPL` / `LGPL`
  / `AGPL` / `GFDL` instead of leaving it unrecognized. Two things worth
  knowing if touching this:
  - **The check is capped at the first 300 characters, not the whole
    file, on purpose.** GPLv3's own text (section 13) references "the GNU
    Affero General Public License" in a compatibility clause -- a
    whole-document search misidentifies plain GPL as AGPL (this was an
    actual bug caught while building this, not a hypothetical). The
    license's own name always appears in the title, so nothing legitimate
    is missed by not scanning the body.
  - **GitHub and GitLab fetch the file differently, and it matters.**
    GitHub uses its dedicated `/repos/{full_name}/license` endpoint, which
    resolves the actual license file case-insensitively and returns its
    content regardless of detection confidence -- exactly what this
    fallback needs, in one call. GitLab has no equivalent shortcut; its
    raw-file endpoint needs an exact-cased git blob path, which
    `_root_listing`'s lowercased set has already lost, so `gitlab_api.py`
    does an extra root-tree lookup (`_find_root_file_exact_name`) to
    recover the real casing -- only in this fallback path, not the common
    case. Don't try to unify these two into one shared implementation;
    they're solving the same problem against genuinely different APIs.
- **`branch_protected` is `bool | None`, not `bool`** -- same pattern as
  `contributors`. `None` means "couldn't determine," not "unprotected."
  In practice this is common: GitHub's branch-protection API is a
  paid-plan feature for *private* repos and 403s regardless of token
  permissions, so most private repos on a free plan read as unknown. See
  `_branch_protection`'s docstring before assuming `False` on a private repo
  means it's actually unprotected.
- **GitLab support (2026-09), opt-in via `--gitlab`.** `gitlab_api.py` is a
  separate module, not a generalization of `github_api.py` -- GitLab's auth
  header, pagination scheme (`X-Next-Page`, not a `Link` header), and
  structural-check endpoints (`repository/tree`, `protected_branches`) are
  different enough that one shared client wasn't worth it. It produces the
  same `RepoInfo` (`platform="gitlab"`), so `health.py` and the renderers
  never branch on platform -- the only platform-aware pieces are (a) what
  `has_ci_config` means at fetch time (`.gitlab-ci.yml` vs `.github/`) and
  (b) the small `(platform)` / `&middot; gitlab` tag the renderers add next
  to a repo's name so GitHub and GitLab rows aren't visually ambiguous.
  Two scope limits carried over from the source script's original GitLab
  support rather than expanded: no GitLab *group* target (only a user's
  projects, via `--gitlab-owner`), and `language` is always blank (GitLab's
  list endpoint doesn't include it; getting it needs a per-project call not
  worth adding for one column). GitLab also has no per-repo paid-plan gate
  on branch protection the way GitHub does for private repos, so the
  `bool | None` "unknown" case there is rarer -- mainly a genuine permission
  problem, not an expected-and-common plan restriction.
- **Token resolution**: `GITHUB_TOKEN` env var first, then `gh auth token`
  as a fallback (`github_api.resolve_token`). Matches actually being logged
  in via the `gh` CLI already, rather than requiring a separate token setup.
- **`render_dashboard.py` is a third renderer, not a replacement for
  `render_html.py`.** `--html` stays a plain static table (every issue as
  text, nothing to break, safe to diff/grep); `--dashboard` is the
  interactive one (filter chips, multi-column sort) meant to actually be
  used in a browser, not just read. Both consume the same `list[RepoHealth]`
  -- no data-layer change needed to add a fourth. CSS/JS live as plain
  (non-f-string) module-level constants (`_STYLE`, `_SCRIPT`) specifically
  so they don't need every literal `{`/`}` escaped as `{{`/`}}`; only the
  HTML body genuinely needs Python interpolation.
- **`render_dashboard`'s CHECKS list is the single source of truth for the
  dashboard**, mirroring how `RepoInfo` is for the data layer: each entry
  is `(key, 2-letter code, label, criterion, group, "grid"|"badge",
  value_fn)`. Add a check there and the legend, filter chips, table column
  (or checklist box), and sort key all pick it up -- no other file to touch
  unless it needs a genuinely new visual treatment.
- **The "no CI config" check exempts forks** (2026-09), same reasoning as
  the contributors check: you didn't choose to set up CI for someone else's
  code, so its absence on a fork isn't a signal about you.
- **The dashboard's fork/originals filter is a separate control from the
  `CHECKS`-driven chips, deliberately** (2026-09, resolves issue #2).
  Every other chip is a pass/fail health signal (missing README, no
  license, ...) with a `data-gaps`/`data-excluded` row attribute driving a
  generic 3-state (off/missing/has) click cycle. "Is a fork" isn't a
  pass/fail check -- it's neutral metadata, and forcing it into the
  `CHECKS` list would make the legend read as if being a fork is an issue
  to fix (missing X/Y). Instead it's two independent toggle buttons
  (`#forks-only-chip` / `#originals-only-chip`, `.fork-toggle` class)
  reading a plain `data-fork="true"/"false"` row attribute, combined by AND
  with the health-check filters in `applyFilters()`. If a future filter is
  similarly "narrow by attribute" rather than "narrow by pass/fail," follow
  this pattern rather than stretching `CHECKS` to fit.
- **Repo names show just `name`, not `owner/name`, for whichever owner is
  most represented in the report** (2026-09) -- `_primary_owner()`
  (duplicated in each of the three renderer modules; they don't share a
  utils module, see the GitLab-client note above for why that's the
  existing pattern here) picks the owner appearing on the most rows via
  `collections.Counter`. A repo under any other owner (a different org, or
  a GitLab account alongside a mostly-GitHub report) keeps the full
  `owner/name` so it isn't mistaken for the primary account's repo of the
  same short name. The full name is never lost -- it's in the link's
  `title` attribute (HTML renderers) or the table title (terminal). Ties
  are broken by whichever owner appears first in the *already-sorted*
  (worst-first) results list, not fetch order -- not worth engineering
  around since a genuine tie (equal repo counts across two owners) is rare
  and the fallback (full name shown) is still correct either way, just not
  maximally compact.

## Open questions

- **Should "no CI config" also exempt tutorial/demo repos** (e.g. a
  single-notebook repo with nothing continuous to test)? There's no clean
  API field for "this is a tutorial repo" -- it'd have to be inferred from
  heuristics (file count, commit count, etc.), which is fuzzier than the
  `is_fork` boolean used for the fork exemption above. Deliberately not
  built until real usage shows the plain check is too noisy for repos like
  that.

## Layout

```
src/repo_healthcheck/
  github_api.py       # GitHub HTTP client -> list[RepoInfo]
  gitlab_api.py        # GitLab HTTP client -> list[RepoInfo] (same shape, platform="gitlab")
  health.py            # RepoInfo -> RepoHealth (issues found), sorted worst-first
  render_terminal.py   # RepoHealth list -> rich table printed to stdout
  render_html.py       # RepoHealth list -> standalone static HTML string
  render_dashboard.py  # RepoHealth list -> standalone interactive HTML (filter + sort)
  cli.py                # typer entry point wiring the above together
tests/
  test_<module>.py      # one file per src module, no network calls (all mocked)
```

## Testing

```bash
uv run pytest                 # everything
uv run ruff check .
uv run mypy
```

No test hits the real GitHub API -- `github_api` functions are monkeypatched
at their public boundary (`fetch_repos`, `resolve_token`) in CLI/integration
tests, and unit-tested directly with mocked HTTP responses elsewhere.

## Conventions

- Type hints everywhere; `from __future__ import annotations`; `pathlib`
  over `os.path`.
- Never hardcode values without explaining why in a comment (see
  `DEFAULT_STALE_DAYS` in `health.py` for the pattern).
- Write for a follow-on developer with no context.
- Flag any speed/performance tradeoff explicitly (see `github_api.py`'s
  module docstring for the per-repo extra-request tradeoff).
- Use `uv`, not pip/poetry.

## Workflow

- One PR per change; branch off `main`.
- Commit trailer: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Personal drafts (blog posts, social copy, anything not project source) go
  in `drafts/` at the repo root. It's gitignored -- never push it to
  GitHub, even incidentally via a broad `git add`.
