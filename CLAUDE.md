# github-admin

A CLI that consolidates every GitHub repo you can see into one health-check
view (README / license / contributors / description / topics / staleness).
See `README.md` for usage and the check list.

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
- **Always fetches `has_readme` and `contributors`** (two extra requests per
  repo beyond the repo-list call). The source script this was adapted from
  (`one-file-tools/tools/repo-inventory/repo_inventory.py`) gates these
  behind `--full` since it's a general-purpose inventory tool where most
  users don't need them. Here they're never optional -- they're exactly
  what the tool exists to check.
- **No GitLab support.** The source script fetches both GitHub and GitLab;
  this tool only manages GitHub repos, so that half was dropped rather than
  carried along unused.
- **Token resolution**: `GITHUB_TOKEN` env var first, then `gh auth token`
  as a fallback (`github_api.resolve_token`). Matches actually being logged
  in via the `gh` CLI already, rather than requiring a separate token setup.

## Layout

```
src/github_admin/
  github_api.py       # GitHub HTTP client -> list[RepoInfo]
  health.py            # RepoInfo -> RepoHealth (issues found), sorted worst-first
  render_terminal.py   # RepoHealth list -> rich table printed to stdout
  render_html.py       # RepoHealth list -> standalone HTML string
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
  module docstring for the `has_readme`/`contributors` tradeoff).
- Use `uv`, not pip/poetry.

## Workflow

- One PR per change; branch off `main`.
- Commit trailer: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
