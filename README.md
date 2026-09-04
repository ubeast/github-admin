# github-admin

Consolidates every GitHub repo you can see into a single health-check view, so
you can spot what's missing (README, CLAUDE.md, branch protection, license,
contributors, description, topics, project structure, staleness) without
clicking through each repo individually.

```bash
$ github-admin
```

prints a table sorted worst-first (most issues on top), so problem repos
never get buried below healthy ones.

Two HTML export options:

- `--html report.html` -- a plain static table, every issue spelled out as text.
- `--dashboard report.html` -- an interactive page: a compact checklist per
  repo, click-to-filter chips (missing / has, multi-select), and click any
  column header to sort (click another header to add it as a tie-breaker,
  building a multi-column sort in click order). This is the one worth
  opening in a browser and actually using, not just reading.

## What it checks

| check | flagged when |
| --- | --- |
| README | repo has no `README*` at the root |
| CLAUDE.md | repo has no `CLAUDE.md` at the root |
| main branch protected | force pushes or branch deletion are allowed on the default branch (see below) |
| license | GitHub doesn't detect a license |
| contributors | only the owner has ever committed (forks are exempt) |
| description | the repo description is empty |
| topics | no topics are set |
| .gitignore | repo has no `.gitignore` at the root |
| tests directory | repo has no `tests/` or `test/` at the root |
| CI config | repo has no `.github/` at the root |
| pyproject.toml | **Python repos only** -- no `pyproject.toml` at the root |
| stale | no push in `--stale-days` days (default 180) |

`src/` layout is detected (`--html` shows it as a column) but never counted
as an issue -- whether a repo should use one depends on its shape (a
deliberate single-file tool, like this project's own source `one-file-tools`,
correctly skips it), which isn't something to auto-enforce.

**"Protected" is a specific, minimal bar**, not "any protection rule
exists": branch protection is on, and both force-push and branch deletion
are disallowed for the default branch. It deliberately does not require PR
review counts or passing status checks -- reasonable for a team, not for
solo work, and this tool covers both. Also: GitHub's branch-protection API
is a **paid-plan feature for private repos** -- it 403s with "Upgrade to
GitHub Pro" regardless of your token's permissions, so most private repos on
a free plan will show `?` (unknown) here rather than a real answer. Public
repos always get a definitive answer.

Archived repos are shown but never flagged -- an archived repo won't be
improved, so there's no point calling out what it's missing.

## Auth

Reads `GITHUB_TOKEN` if set, otherwise falls back to `gh auth token` (so if
you're already logged in via the `gh` CLI, no extra setup is needed). Token
scope: classic `repo` (to see private repos) or none (public only);
fine-grained needs read-only "Contents" + "Metadata".

By default it fetches everything the token can see -- your own repos plus
every org you're a member of -- in one call (GitHub's
`affiliation=owner,collaborator,organization_member` does this natively, no
per-org looping needed). Pass `--owner NAME` to instead check one specific
user's/org's public repos.

## Install

```bash
uv sync
uv run github-admin --help
```

## Tests

```bash
uv run pytest
```

## Roadmap

This first pass is read-only: collect and display. A later iteration may add
bulk-fix actions (e.g. apply a license, add topics) once it's clear from real
usage what "fix" needs to support -- see the project's CLAUDE.md for why that
decision is deferred rather than built in from the start.
