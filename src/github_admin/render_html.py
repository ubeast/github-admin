"""Render health-check results as a standalone HTML report."""

from __future__ import annotations

from datetime import datetime
from html import escape

from github_admin.health import RepoHealth

__all__ = ["render"]

_STYLE = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, system-ui, sans-serif; margin: 2rem; background: #fafafa; color: #1a1a1a; }
h1 { font-size: 1.3rem; }
.meta { color: #666; margin-bottom: 1.5rem; }
table { border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
th, td { padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid #eee; font-size: 0.9rem; }
th { background: #f0f0f0; position: sticky; top: 0; }
tr.archived { opacity: 0.5; }
tr.unhealthy { background: #fff8f0; }
.ok { color: #1a7f37; font-weight: bold; }
.bad { color: #cf222e; font-weight: bold; }
.issues { color: #9a6700; }
.healthy { color: #1a7f37; }
td.num { text-align: right; }
td.center { text-align: center; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
@media (prefers-color-scheme: dark) {
  body { background: #0d1117; color: #e6edf3; }
  table { background: #161b22; box-shadow: none; }
  th { background: #21262d; }
  th, td { border-bottom-color: #30363d; }
  tr.unhealthy { background: #1c1712; }
  a { color: #4493f8; }
}
"""


def _flag(ok: bool) -> str:
    return '<span class="ok">✓</span>' if ok else '<span class="bad">✗</span>'


def render(results: list[RepoHealth]) -> str:
    """Return a complete, self-contained HTML document as a string."""
    unhealthy = sum(1 for h in results if not h.is_healthy)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = []
    for h in results:
        r = h.repo
        classes = []
        if r.archived:
            classes.append("archived")
        elif not h.is_healthy:
            classes.append("unhealthy")
        row_class = f' class="{" ".join(classes)}"' if classes else ""

        contributors = "?" if r.contributors is None else str(r.contributors)
        if h.is_healthy:
            issue_text = '<span class="healthy">ok</span>'
        else:
            issue_text = f'<span class="issues">{escape("; ".join(h.issues))}</span>'
        archived_note = " (archived)" if r.archived else ""

        rows.append(
            f"<tr{row_class}>"
            f'<td><a href="{escape(r.url)}">{escape(r.full_name)}</a>{archived_note}</td>'
            f'<td class="center">{_flag(r.has_readme)}</td>'
            f'<td class="center">{_flag(bool(r.license))}</td>'
            f'<td class="num">{contributors}</td>'
            f'<td class="num">{r.forks}</td>'
            f'<td class="center">{_flag(bool(r.description))}</td>'
            f'<td class="center">{_flag(bool(r.topics))}</td>'
            f"<td>{escape(r.pushed)}</td>"
            f"<td>{issue_text}</td>"
            f"</tr>"
        )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>github-admin report</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>github-admin -- repo health report</h1>
<p class="meta">{len(results)} repos, {unhealthy} with at least one issue. Generated {generated}.</p>
<table>
<thead>
<tr>
<th>repo</th><th>readme</th><th>license</th><th>contributors</th><th>forks</th>
<th>description</th><th>topics</th><th>pushed</th><th>issues</th>
</tr>
</thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
</body>
</html>
"""
