"""Render health-check results as a self-contained, interactive HTML dashboard.

Unlike ``render_html.py`` (a plain static table -- every issue as text), this
is meant to be *used*, not just read: a compact multi-box checklist per repo,
click-to-filter chips (missing / has, multi-select), and click-to-sort
column headers (multi-column, click order sets priority). All state lives in
inline JavaScript against ``data-*`` attributes -- no build step, no
framework, works by opening the file in a browser.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from html import escape

from github_admin.health import RepoHealth

__all__ = ["render"]

# Every check the dashboard displays, in one place. "grid" checks are pure
# booleans and render as the compact multi-box glyph, grouped by `group`;
# "badge" checks are tri-state (True / False / None-meaning-not-applicable-
# or-unknown) and get their own labeled column instead of a box, so a third
# state never has to be squeezed into a two-state glyph.
_CheckFn = Callable[[RepoHealth], "bool | None"]
CHECKS: list[tuple[str, str, str, str, str, str, _CheckFn]] = [
    ("readme", "RM", "README", "a README file exists at the repo root", "docs", "grid",
     lambda h: bool(h.repo.has_readme)),
    ("claude_md", "CM", "CLAUDE.md", "repo has a CLAUDE.md for Claude Code", "docs", "grid",
     lambda h: bool(h.repo.has_claude_md)),
    ("license", "LC", "License", "GitHub detects a recognized license", "standards", "grid",
     lambda h: bool(h.repo.license)),
    ("description", "DS", "Description", "the repo's About description is filled in", "standards", "grid",
     lambda h: bool(h.repo.description)),
    ("topics", "TP", "Topics", "at least one topic is set", "standards", "grid",
     lambda h: bool(h.repo.topics)),
    ("gitignore", "GI", ".gitignore", "a .gitignore file exists at the repo root", "structure", "grid",
     lambda h: bool(h.repo.has_gitignore)),
    ("tests", "TS", "Tests", "a tests/ or test/ directory exists", "structure", "grid",
     lambda h: bool(h.repo.has_tests_dir)),
    ("ci", "CI", "CI config", "a .github/ directory exists (Actions workflows)", "structure", "grid",
     lambda h: bool(h.repo.has_ci_config)),
    ("contributors", "CN", "Contributors", "someone besides the owner has committed", "activity", "grid",
     lambda h: (h.repo.contributors or 0) > 1 or h.repo.is_fork),
    ("fresh", "AC", "Active", "pushed within the last 180 days", "activity", "grid",
     lambda h: not any(i.startswith("stale") for i in h.issues)),
    ("protected", "PR", "Branch protected",
     "force-push and deletion disallowed on the default branch — private repos on a free GitHub plan "
     "can't be checked at all (shown as unknown, not unprotected)",
     "governance", "badge", lambda h: h.repo.branch_protected),
    ("pyproject", "PY", "pyproject.toml",
     "Python repos only — has a pyproject.toml at the root", "governance", "badge",
     lambda h: bool(h.repo.has_pyproject) if h.repo.language == "Python" else None),
]

GRID_CHECKS = [c for c in CHECKS if c[5] == "grid"]
BADGE_CHECKS = [c for c in CHECKS if c[5] == "badge"]

GROUP_ORDER = ["docs", "standards", "structure", "activity"]
GROUP_LABELS = {"docs": "Docs", "standards": "Standards", "structure": "Structure", "activity": "Activity"}


def _license_label(lic: str) -> str:
    if not lic:
        return "missing"
    if lic == "NOASSERTION":
        return "unrecognized"
    return lic


def _sev_class(n: int) -> str:
    if n == 0:
        return "sev-good"
    if n <= 2:
        return "sev-warn"
    return "sev-bad"


def _box(v: bool) -> str:
    cls = "box on" if v else "box"
    return f'<span class="{cls}" aria-hidden="true"></span>'


def _badge_pill(key: str, v: bool | None) -> str:
    if key == "protected":
        text = {True: "protected", False: "not protected", None: "unknown"}[v]
    else:
        text = {True: "yes", False: "no", None: "n/a"}[v]
    cls = {True: "good", False: "bad", None: "na"}[v]
    return f'<span class="badge-pill {cls}">{escape(text)}</span>'


def _with_group_gaps(
    items: list[tuple[str, str, str, str, str, str, _CheckFn]],
    render_item: Callable[[tuple[str, str, str, str, str, str, _CheckFn]], str],
) -> str:
    """Join rendered items, inserting a small gap wherever the group changes."""
    out: list[str] = []
    prev_group: str | None = None
    for item in items:
        group = item[4]
        if prev_group is not None and group != prev_group:
            out.append('<span class="chk-group-gap"></span>')
        out.append(render_item(item))
        prev_group = group
    return "".join(out)


def _sortable_th(key: str, label: str, *, numeric: bool = False, title: str = "") -> str:
    title_attr = f' title="{escape(title)}"' if title else ""
    return (
        f'<th class="sortable" data-sort-key="{key}" data-numeric="{"1" if numeric else "0"}" '
        f'tabindex="0" role="button"{title_attr}>{label}<span class="sort-ind"></span></th>'
    )


def _counts_for(results: list[RepoHealth], fn: _CheckFn) -> tuple[int, int, int]:
    """(missing, has, not-applicable/unknown) counts across all results."""
    missing = sum(1 for h in results if fn(h) is False)
    has = sum(1 for h in results if fn(h) is True)
    na = sum(1 for h in results if fn(h) is None)
    return missing, has, na


def render(results: list[RepoHealth]) -> str:
    """Return a complete, self-contained HTML document as a string."""
    total = len(results)
    healthy = sum(1 for h in results if h.is_healthy)
    avg_issues = (sum(h.issue_count for h in results) / total) if total else 0.0
    counts = {key: _counts_for(results, fn) for key, *_rest, fn in CHECKS}
    owners = ", ".join(sorted({h.repo.owner for h in results})) or "none"
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    chk_legend_header = _with_group_gaps(
        GRID_CHECKS, lambda c: f'<span class="chk-legend" title="{c[2]} — {c[3]}">{c[1]}</span>'
    )

    rows: list[str] = []
    for h in results:
        repo = h.repo
        values: dict[str, bool | None] = {key: fn(h) for key, *_rest, fn in CHECKS}
        gap_keys = " ".join(k for k, v in values.items() if v is False)
        excluded_keys = " ".join(k for k, v in values.items() if v is None)

        n = h.issue_count
        grid_parts: list[str] = []
        prev_group: str | None = None
        for gkey, _letter, glabel, _crit, ggroup, _kind, _fn in GRID_CHECKS:
            if prev_group is not None and ggroup != prev_group:
                grid_parts.append('<span class="chk-group-gap"></span>')
            gok = bool(values[gkey])
            grid_parts.append(
                f'<span class="chk {"yes" if gok else "no"}" data-gap="{gkey}" title="{glabel}">{_box(gok)}</span>'
            )
            prev_group = ggroup
        grid_badges = "".join(grid_parts)
        badge_cells = "".join(f'<td class="col-badge">{_badge_pill(key, values[key])}</td>' for key, *_r in BADGE_CHECKS)

        lic = _license_label(repo.license)
        contrib = repo.contributors if repo.contributors is not None else "?"
        fork_note = " &middot; fork" if repo.is_fork else ""
        desc = escape(repo.description) if repo.description else '<span class="muted">no description</span>'
        topics_html = (
            "".join(f'<span class="topic">{escape(t)}</span>' for t in repo.topics[:4])
            if repo.topics
            else '<span class="muted">&mdash;</span>'
        )
        if len(repo.topics) > 4:
            topics_html += f'<span class="topic muted">+{len(repo.topics) - 4}</span>'

        src_html = (
            '<span class="info-yes">src/</span>' if repo.has_src_layout else '<span class="muted">&mdash;</span>'
        )

        # Sort keys: tri-state badges rank worst-to-best (missing < unknown/
        # n-a < has) so ascending order surfaces problems first, matching
        # the dashboard's worst-first bias. Unknown contributor counts sort
        # to the front (-1) for the same reason.
        tri_rank = {False: 0, None: 1, True: 2}
        sort_attrs = {
            "repo": escape(repo.full_name.lower()),
            "protected": tri_rank[values["protected"]],
            "pyproject": tri_rank[values["pyproject"]],
            "license": escape(lic.lower()),
            "contributors": repo.contributors if repo.contributors is not None else -1,
            "forks": repo.forks,
            "topics": len(repo.topics),
            "src": 1 if repo.has_src_layout else 0,
            "pushed": escape(repo.pushed),
            "gaps": n,
        }
        sort_data = " ".join(f'data-sort-{k}="{v}"' for k, v in sort_attrs.items())

        rows.append(f"""
<tr class="{_sev_class(n)}" data-name="{escape(repo.full_name.lower())}" data-gaps="{gap_keys}" data-excluded="{excluded_keys}" {sort_data}>
  <td class="stripe" aria-hidden="true"></td>
  <td class="col-repo">
    <a class="repo-link" href="{escape(repo.url)}">{escape(repo.full_name)}</a>{fork_note}
    <div class="desc">{desc}</div>
  </td>
  <td class="col-checks">{grid_badges}</td>
  {badge_cells}
  <td class="col-license"><span class="lic {"missing" if not repo.license else ""}">{escape(lic)}</span></td>
  <td class="col-num">{contrib}</td>
  <td class="col-num">{repo.forks}</td>
  <td class="col-topics">{topics_html}</td>
  <td class="col-src" title="informational only, not counted as an issue">{src_html}</td>
  <td class="col-pushed">{escape(repo.pushed)}</td>
  <td class="col-gaps"><span class="gap-count {_sev_class(n)}">{n if n else "clean"}</span></td>
</tr>""")

    legend_items = []
    for key, letter, label, crit, _group, _kind, _fn in CHECKS:
        missing, _has, na = counts[key]
        na_note = f" &middot; {na} n/a" if na else ""
        legend_items.append(f"""<div class="legend-item">
        <span class="legend-letter">{letter}</span>
        <div>
          <div class="legend-label">{label}</div>
          <div class="legend-crit">{crit}</div>
        </div>
        <div class="legend-gap">{missing}/{total} missing{na_note}</div>
      </div>""")
    checklist_legend = "".join(legend_items)

    chips = "".join(
        f"""<button class="chip" data-filter="{key}" data-missing="{counts[key][0]}" data-has="{counts[key][1]}">
        <span class="chip-icon" aria-hidden="true"></span>{label} <span class="chip-n">{counts[key][0]}</span>
      </button>"""
        for key, _code, label, _crit, _group, _kind, _fn in CHECKS
    )

    top_gap_key = max(counts, key=lambda k: counts[k][0]) if counts else ""
    top_gap_label = next((label for key, _c, label, _cr, _g, _k, _fn in CHECKS if key == top_gap_key), "")

    badge_headers = "".join(
        _sortable_th(key, label, numeric=True, title=crit) for key, _code, label, crit, _group, _kind, _fn in BADGE_CHECKS
    )
    th_repo = _sortable_th("repo", "Repo")
    th_license = _sortable_th("license", "License type")
    th_contrib = _sortable_th("contributors", "Contrib.", numeric=True)
    th_forks = _sortable_th("forks", "Forks", numeric=True)
    th_topics = _sortable_th("topics", "Topics", numeric=True, title="sorts by topic count")
    th_src = _sortable_th("src", "src/", numeric=True, title="informational only, not counted as an issue")
    th_pushed = _sortable_th("pushed", "Last push")
    th_gaps = _sortable_th("gaps", "Gaps", numeric=True)

    by_group: dict[str, list[str]] = {g: [] for g in GROUP_ORDER}
    for _key, code, label, _crit, group, _kind, _fn in GRID_CHECKS:
        by_group[group].append(f"{code}={label}")
    checklist_key = " &nbsp;|&nbsp; ".join(
        f"<b>{GROUP_LABELS[g]}:</b> " + ", ".join(by_group[g]) for g in GROUP_ORDER if by_group[g]
    )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>github-admin dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,400;0,600;0,700;1,500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>{_STYLE}</style>
</head>
<body>
<div class="wrap">
  <div class="masthead">
    <div>
      <p class="eyebrow">github-admin &middot; repo audit</p>
      <h1>What every repo should have</h1>
    </div>
    <div class="meta">
      scope: <b>{escape(owners)}</b><br>
      generated <b>{generated}</b><br>
      <b>{total}</b> repos audited
    </div>
  </div>

  <div class="stats">
    <div class="stat">
      <div class="stat-value">{total}</div>
      <div class="stat-label">repos audited</div>
    </div>
    <div class="stat">
      <div class="stat-value bad">{total - healthy}</div>
      <div class="stat-label">have at least one gap</div>
    </div>
    <div class="stat">
      <div class="stat-value">{avg_issues:.1f}</div>
      <div class="stat-label">avg. gaps per repo</div>
    </div>
    <div class="stat">
      <div class="stat-value accent">{escape(top_gap_label)}</div>
      <div class="stat-label">most common gap &mdash; {counts[top_gap_key][0] if top_gap_key else 0}/{total} repos</div>
    </div>
  </div>

  <section class="block">
    <h2>The checklist</h2>
    <p class="block-sub">Every standard this account's repos are measured against, grouped by kind. Archived repos are exempt from all of it &mdash; they won't be improved, so nothing here is held against them. Branch-protection and pyproject.toml can legitimately read "n/a" (a paid-plan limit on private repos, or a non-Python project) rather than pass/fail.</p>
    <p class="legend-note">Reference only, not clickable &mdash; use the filters in the table below to narrow the list.</p>
    <div class="legend">
      {checklist_legend}
    </div>
  </section>

  <section class="block">
    <h2>Every repo, worst first</h2>
    <p class="block-sub">Sorted by gap count so the repos needing the most attention surface at the top. Click a checklist item below to filter to just the repos missing it, or click any column header to sort by it &mdash; click another header to add it as a tie-breaker, click a sorted header again to reverse it, a third time to drop it.</p>
    <p class="legend-note">Checklist column codes &mdash; {checklist_key}</p>

    <div class="controls">
      <input id="search" type="text" placeholder="filter by repo name&hellip;" aria-label="Filter by repo name">
      {chips}
      <button id="clear-filter">clear filter</button>
      <button id="reset-sort">reset sort</button>
      <span id="result-count"></span>
      <div class="chip-hint">click once for <b style="color: var(--bad)">missing</b>, twice for <b style="color: var(--good)">has it</b>, three times to clear &mdash; combine multiple. Rows shown "n/a" for a filter never match either state.</div>
    </div>

    <div class="table-scroll">
      <table id="repo-table">
        <thead>
          <tr>
            <th></th>
            {th_repo}
            <th class="col-checks-header">{chk_legend_header}</th>
            {badge_headers}
            {th_license}
            {th_contrib}
            {th_forks}
            {th_topics}
            {th_src}
            {th_pushed}
            {th_gaps}
          </tr>
        </thead>
        <tbody>
          {"".join(rows)}
        </tbody>
      </table>
    </div>
  </section>

  <footer>
    Generated locally by <a href="https://github.com/ubeast/github-admin">github-admin</a> &mdash; read-only, no changes were made to any repo.
  </footer>
</div>

<script>{_SCRIPT}</script>
</body>
</html>
"""


_STYLE = """
:root {
  --paper: #f1f3ee;
  --surface: #ffffff;
  --surface-2: #eaece5;
  --ink: #1e2a22;
  --ink-soft: #55635a;
  --line: #d9dfd2;
  --accent: #2b5d6b;
  --accent-soft: #dce9ea;
  --good: #2f7a4f;
  --good-soft: #e3f0e6;
  --warn: #a8721f;
  --warn-soft: #f5ead4;
  --bad: #b23a2e;
  --bad-soft: #f6e1dd;
  --na: #8c959f;
  --na-soft: #eceef0;
  --shadow: 0 1px 2px rgba(30,42,34,0.06), 0 6px 20px rgba(30,42,34,0.05);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #121814;
    --surface: #1a231c;
    --surface-2: #212b22;
    --ink: #e7ede4;
    --ink-soft: #a7b4a9;
    --line: #2b3830;
    --accent: #7fc0cd;
    --accent-soft: #1d3338;
    --good: #7dd6a0;
    --good-soft: #182a1f;
    --warn: #e0ae5c;
    --warn-soft: #2e2313;
    --bad: #e2776a;
    --bad-soft: #331e1a;
    --na: #7d8590;
    --na-soft: #21262c;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 6px 20px rgba(0,0,0,0.35);
  }
}
:root[data-theme="dark"] {
  --paper: #121814;
  --surface: #1a231c;
  --surface-2: #212b22;
  --ink: #e7ede4;
  --ink-soft: #a7b4a9;
  --line: #2b3830;
  --accent: #7fc0cd;
  --accent-soft: #1d3338;
  --good: #7dd6a0;
  --good-soft: #182a1f;
  --warn: #e0ae5c;
  --warn-soft: #2e2313;
  --bad: #e2776a;
  --bad-soft: #331e1a;
  --na: #7d8590;
  --na-soft: #21262c;
  --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 6px 20px rgba(0,0,0,0.35);
}

* { box-sizing: border-box; }
body {
  background: var(--paper);
  color: var(--ink);
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  margin: 0;
  padding: 2.5rem 1.5rem 4rem;
}
.wrap { max-width: 1320px; margin: 0 auto; }

.masthead {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-end;
  gap: 1rem;
  border-bottom: 2px solid var(--ink);
  padding-bottom: 1.1rem;
  margin-bottom: 1.75rem;
}
h1 {
  font-family: "Fraunces", Georgia, serif;
  font-weight: 600;
  font-size: clamp(1.7rem, 3vw, 2.3rem);
  margin: 0;
  text-wrap: balance;
  letter-spacing: -0.01em;
}
.eyebrow {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.72rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 0.35rem;
}
.meta {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.82rem;
  color: var(--ink-soft);
  text-align: right;
  line-height: 1.6;
}
.meta b { color: var(--ink); font-weight: 600; }

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 2.25rem;
  box-shadow: var(--shadow);
}
.stat { background: var(--surface); padding: 1.1rem 1.3rem; }
.stat-value {
  font-family: "IBM Plex Mono", monospace;
  font-size: 1.7rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.stat-value.bad { color: var(--bad); }
.stat-value.accent { color: var(--accent); }
.stat-label { font-size: 0.78rem; color: var(--ink-soft); margin-top: 0.45rem; }

section.block { margin-bottom: 2.25rem; }
h2 {
  font-family: "Fraunces", Georgia, serif;
  font-weight: 600;
  font-size: 1.15rem;
  margin: 0 0 0.2rem;
}
.block-sub { font-size: 0.85rem; color: var(--ink-soft); margin: 0 0 1rem; max-width: 70ch; }

.legend {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 0.75rem;
}
.legend-item {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.8rem 0.9rem;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.15rem 0.7rem;
  align-items: start;
}
.legend-letter {
  width: 26px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  margin-top: 0.1rem;
  background: var(--accent-soft);
  color: var(--accent);
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.68rem;
  font-weight: 600;
}
.legend-note { font-size: 0.76rem; font-style: italic; color: var(--ink-soft); opacity: 0.8; margin: 0 0 1rem; }
.legend-label { font-weight: 600; font-size: 0.92rem; }
.legend-crit { font-size: 0.78rem; color: var(--ink-soft); margin-top: 0.1rem; }
.legend-gap {
  grid-column: 2;
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.72rem;
  color: var(--accent);
  margin-top: 0.35rem;
}

.controls { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center; margin-bottom: 1rem; }
#search {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.85rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--surface);
  color: var(--ink);
  min-width: 220px;
}
#search:focus-visible, .chip:focus-visible, #clear-filter:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
.chip {
  font-family: "IBM Plex Sans", sans-serif;
  font-size: 0.78rem;
  padding: 0.4rem 0.7rem 0.4rem 0.55rem;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-soft);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}
.chip:hover { border-color: var(--accent); color: var(--ink); }
.chip-icon { width: 13px; height: 13px; border-radius: 3px; border: 1.5px solid var(--line); flex: none; }
.chip.state-missing { background: var(--bad-soft); border-color: var(--bad); color: var(--bad); }
.chip.state-missing .chip-icon { background: var(--bad); border-color: var(--bad); }
.chip.state-has { background: var(--good-soft); border-color: var(--good); color: var(--good); }
.chip.state-has .chip-icon { background: var(--good); border-color: var(--good); }
.chip-n { font-family: "IBM Plex Mono", monospace; opacity: 0.8; }
.chip-hint { font-size: 0.72rem; color: var(--ink-soft); opacity: 0.75; width: 100%; }
#clear-filter, #reset-sort {
  font-family: "IBM Plex Sans", sans-serif;
  font-size: 0.78rem;
  color: var(--accent);
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  padding: 0.4rem 0.2rem;
  display: none;
}
#result-count { font-family: "IBM Plex Mono", monospace; font-size: 0.76rem; color: var(--ink-soft); margin-left: auto; }

.table-scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; box-shadow: var(--shadow); }
table { border-collapse: collapse; width: 100%; min-width: 1180px; background: var(--surface); }
thead th {
  position: sticky;
  top: 0;
  background: var(--surface-2);
  text-align: left;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--ink-soft);
  font-weight: 600;
  padding: 0.7rem 0.7rem;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
th.sortable { cursor: pointer; user-select: none; }
th.sortable:hover { color: var(--ink); background: var(--accent-soft); }
th.sortable:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.sort-ind {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: 0.3rem;
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.68rem;
  color: var(--accent);
  vertical-align: middle;
}
.sort-ind .sort-arrow { font-size: 0.62rem; }
.sort-ind .sort-priority {
  background: var(--accent);
  color: var(--surface);
  border-radius: 999px;
  width: 12px;
  height: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.58rem;
  line-height: 1;
}
tbody td { padding: 0.65rem 0.7rem; border-bottom: 1px solid var(--line); vertical-align: top; font-size: 0.86rem; }
tbody tr:last-child td { border-bottom: none; }
tbody tr.hidden { display: none; }
td.stripe { width: 4px; padding: 0; }
tr.sev-bad td.stripe { background: var(--bad); }
tr.sev-warn td.stripe { background: var(--warn); }
tr.sev-good td.stripe { background: var(--good); }

.col-repo { min-width: 220px; }
.repo-link { font-family: "IBM Plex Mono", monospace; font-size: 0.86rem; font-weight: 500; color: var(--ink); text-decoration: none; }
.repo-link:hover { color: var(--accent); text-decoration: underline; }
.desc { font-size: 0.78rem; color: var(--ink-soft); margin-top: 0.2rem; max-width: 34ch; }
.muted { color: var(--ink-soft); opacity: 0.7; }

th.col-checks-header { white-space: nowrap; text-transform: none; letter-spacing: normal; }
.chk-legend {
  display: inline-block;
  width: 16px;
  margin-right: 3px;
  text-align: center;
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.58rem;
  color: var(--accent);
  cursor: help;
}
.col-checks { white-space: nowrap; }
.chk { display: inline-block; margin-right: 3px; }
.chk-group-gap { display: inline-block; width: 8px; }
.box {
  display: inline-block;
  width: 13px;
  height: 13px;
  border: 1.5px solid var(--ink-soft);
  border-radius: 3px;
  background: transparent;
  position: relative;
}
.box.on { background: var(--good); border-color: var(--good); }
.box.on::after {
  content: "";
  position: absolute;
  left: 3px; top: 0px;
  width: 4px; height: 8px;
  border-right: 1.5px solid var(--surface);
  border-bottom: 1.5px solid var(--surface);
  transform: rotate(40deg);
}
.chk.no .box { border-color: var(--bad); background: var(--bad-soft); }

.col-badge { white-space: nowrap; }
.badge-pill { font-family: "IBM Plex Mono", monospace; font-size: 0.74rem; padding: 0.15rem 0.5rem; border-radius: 999px; display: inline-block; }
.badge-pill.good { background: var(--good-soft); color: var(--good); }
.badge-pill.bad { background: var(--bad-soft); color: var(--bad); }
.badge-pill.na { background: var(--na-soft); color: var(--na); }

.col-license .lic { font-family: "IBM Plex Mono", monospace; font-size: 0.78rem; padding: 0.15rem 0.45rem; border-radius: 5px; background: var(--good-soft); color: var(--good); }
.col-license .lic.missing { background: var(--bad-soft); color: var(--bad); }

.col-num { font-family: "IBM Plex Mono", monospace; font-variant-numeric: tabular-nums; text-align: right; }

.col-topics { max-width: 200px; }
.topic {
  display: inline-block;
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.7rem;
  background: var(--accent-soft);
  color: var(--accent);
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  margin: 0 3px 3px 0;
}
.topic.muted { background: transparent; color: var(--ink-soft); padding-left: 0; }

.col-src { font-family: "IBM Plex Mono", monospace; font-size: 0.78rem; }
.info-yes { color: var(--accent); }

.col-pushed { font-family: "IBM Plex Mono", monospace; font-size: 0.78rem; color: var(--ink-soft); white-space: nowrap; }

.gap-count { font-family: "IBM Plex Mono", monospace; font-weight: 600; font-size: 0.82rem; padding: 0.15rem 0.5rem; border-radius: 999px; }
.gap-count.sev-bad { background: var(--bad-soft); color: var(--bad); }
.gap-count.sev-warn { background: var(--warn-soft); color: var(--warn); }
.gap-count.sev-good { background: var(--good-soft); color: var(--good); }

footer { margin-top: 2rem; font-size: 0.76rem; color: var(--ink-soft); text-align: center; }
footer a { color: var(--accent); }

@media (prefers-reduced-motion: no-preference) {
  tbody tr { transition: opacity 0.12s ease; }
}
"""

_SCRIPT = """
(function() {
  // Each chip cycles through three states on click: 0 = off, 1 = "show
  // repos missing this", 2 = "show repos that have this". A row listed in
  // data-excluded for a key (branch-protection unknown, or pyproject on a
  // non-Python repo) never matches either state for that key -- it isn't
  // "missing" or "has", it's not determinable/applicable. Multiple chips
  // combine with AND, so e.g. README=has + License=missing finds repos
  // that have a README but still need a license.
  var rows = Array.prototype.slice.call(document.querySelectorAll('#repo-table tbody tr'));
  var search = document.getElementById('search');
  var chips = Array.prototype.slice.call(document.querySelectorAll('.chip'));
  var clearBtn = document.getElementById('clear-filter');
  var resultCount = document.getElementById('result-count');
  var filters = {}; // key -> 1 (missing) | 2 (has)

  function updateChipVisual(chip) {
    var key = chip.getAttribute('data-filter');
    var state = filters[key] || 0;
    chip.classList.remove('state-missing', 'state-has');
    var n = chip.querySelector('.chip-n');
    if (state === 1) {
      chip.classList.add('state-missing');
      n.textContent = chip.getAttribute('data-missing');
    } else if (state === 2) {
      chip.classList.add('state-has');
      n.textContent = chip.getAttribute('data-has');
    } else {
      n.textContent = chip.getAttribute('data-missing');
    }
  }

  function applyFilters() {
    var term = search.value.trim().toLowerCase();
    var keys = Object.keys(filters);
    var visible = 0;
    rows.forEach(function(row) {
      var nameMatch = !term || row.getAttribute('data-name').indexOf(term) !== -1;
      var gapSet = ' ' + row.getAttribute('data-gaps') + ' ';
      var excludedSet = ' ' + row.getAttribute('data-excluded') + ' ';
      var gapMatch = keys.every(function(key) {
        if (excludedSet.indexOf(' ' + key + ' ') !== -1) return false;
        var missing = gapSet.indexOf(' ' + key + ' ') !== -1;
        return filters[key] === 1 ? missing : !missing;
      });
      var show = nameMatch && gapMatch;
      row.classList.toggle('hidden', !show);
      if (show) visible++;
    });
    resultCount.textContent = visible + ' / ' + rows.length + ' shown';
    clearBtn.style.display = (keys.length || term) ? 'inline-block' : 'none';
  }

  search.addEventListener('input', applyFilters);

  chips.forEach(function(chip) {
    chip.addEventListener('click', function() {
      var key = chip.getAttribute('data-filter');
      var state = (filters[key] || 0) + 1;
      if (state > 2) {
        delete filters[key];
      } else {
        filters[key] = state;
      }
      updateChipVisual(chip);
      applyFilters();
    });
  });

  clearBtn.addEventListener('click', function() {
    filters = {};
    search.value = '';
    chips.forEach(updateChipVisual);
    applyFilters();
  });

  // Multi-column sort: clicking a header makes it the primary sort key
  // (moved to the front) while keeping any other already-active columns as
  // lower-priority tie-breakers, so plain clicks (no modifier key) build up
  // a multi-column sort in click order -- most recently clicked wins ties
  // first. Clicking the same column again flips its direction; a third
  // click drops it from the sort and the others shift up in priority.
  var tbody = document.querySelector('#repo-table tbody');
  var sortHeaders = Array.prototype.slice.call(document.querySelectorAll('th.sortable'));
  var resetSortBtn = document.getElementById('reset-sort');
  var DEFAULT_SORT = [{ key: 'gaps', dir: 'desc' }]; // matches the server-rendered default order
  var sortState = [{ key: 'gaps', dir: 'desc' }];

  function isDefaultSort() {
    return sortState.length === 1 && sortState[0].key === DEFAULT_SORT[0].key && sortState[0].dir === DEFAULT_SORT[0].dir;
  }

  function renderSortIndicators() {
    sortHeaders.forEach(function(th) {
      var key = th.getAttribute('data-sort-key');
      var ind = th.querySelector('.sort-ind');
      var idx = -1;
      for (var i = 0; i < sortState.length; i++) {
        if (sortState[i].key === key) { idx = i; break; }
      }
      if (idx === -1) {
        ind.innerHTML = '';
        return;
      }
      var arrow = sortState[idx].dir === 'asc' ? '▲' : '▼';
      var priority = sortState.length > 1 ? '<span class="sort-priority">' + (idx + 1) + '</span>' : '';
      ind.innerHTML = '<span class="sort-arrow">' + arrow + '</span>' + priority;
    });
    resetSortBtn.style.display = isDefaultSort() ? 'none' : 'inline-block';
  }

  function sortRows() {
    var sorted = rows.slice().sort(function(a, b) {
      for (var i = 0; i < sortState.length; i++) {
        var s = sortState[i];
        var th = document.querySelector('th[data-sort-key="' + s.key + '"]');
        var numeric = th && th.getAttribute('data-numeric') === '1';
        var av = a.getAttribute('data-sort-' + s.key);
        var bv = b.getAttribute('data-sort-' + s.key);
        var cmp;
        if (numeric) {
          cmp = parseFloat(av) - parseFloat(bv);
        } else {
          cmp = av < bv ? -1 : (av > bv ? 1 : 0);
        }
        if (cmp !== 0) return s.dir === 'asc' ? cmp : -cmp;
      }
      var an = a.getAttribute('data-sort-repo'), bn = b.getAttribute('data-sort-repo');
      return an < bn ? -1 : (an > bn ? 1 : 0);
    });
    sorted.forEach(function(row) { tbody.appendChild(row); });
  }

  sortHeaders.forEach(function(th) {
    function activate() {
      var key = th.getAttribute('data-sort-key');
      var idx = -1;
      for (var i = 0; i < sortState.length; i++) {
        if (sortState[i].key === key) { idx = i; break; }
      }
      if (idx === -1) {
        sortState.unshift({ key: key, dir: 'asc' });
      } else if (sortState[idx].dir === 'asc') {
        var entry = sortState.splice(idx, 1)[0];
        entry.dir = 'desc';
        sortState.unshift(entry);
      } else {
        sortState.splice(idx, 1);
      }
      renderSortIndicators();
      sortRows();
    }
    th.addEventListener('click', activate);
    th.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); }
    });
  });

  resetSortBtn.addEventListener('click', function() {
    sortState = [{ key: DEFAULT_SORT[0].key, dir: DEFAULT_SORT[0].dir }];
    renderSortIndicators();
    sortRows();
  });

  renderSortIndicators();
  applyFilters();
})();
"""
