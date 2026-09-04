# github-admin

Consolidates every GitHub repo you can see into a single health-check view, so
you can spot what's missing (README, license, contributors, description,
topics, staleness) without clicking through each repo individually.

```bash
$ github-admin
```

prints a table sorted worst-first (most issues on top), so problem repos
never get buried below healthy ones. Pass `--html report.html` to also save a
browser-viewable copy.

## What it checks

| check | flagged when |
| --- | --- |
| README | repo has no `README` at the default branch root |
| license | GitHub doesn't detect a license |
| contributors | only the owner has ever committed (forks are exempt) |
| description | the repo description is empty |
| topics | no topics are set |
| stale | no push in `--stale-days` days (default 180) |

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
