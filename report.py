"""Build a standalone, self-contained HTML failure-analysis report.

The output mirrors the style of the example FeatBench report: a dark themed
page with overview stat cards, a failure-by-tag bar chart, prioritized action
cards, and a per-sample table. Everything is inlined (CSS in a <style> block,
no external assets) so the file opens on its own.
"""

from __future__ import annotations

import html
from typing import Any

# Priority -> (label colour, css var name). High first.
PRIORITY_ORDER = ["High", "Medium", "Low"]
PRIORITY_COLORS = {
    "High": "#ff5a65",
    "Medium": "#ffab40",
    "Low": "#ffd740",
}
# Cycling palette for the tag bars.
BAR_COLORS = ["red", "orange", "yellow", "purple", "blue", "pink", "green"]

_CSS = """
:root {
  --bg:#0f1117; --card:#1a1d2e; --card2:#222640; --border:#2d3154;
  --text:#e2e4f0; --text2:#9498b3; --accent:#6c72ff; --accent2:#4fc3f7;
  --red:#ff5a65; --green:#4caf50; --orange:#ffab40; --yellow:#ffd740;
  --purple:#b388ff; --pink:#ff80ab;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; line-height:1.6; }
.container { max-width:1400px; margin:0 auto; padding:24px; }
h1 { font-size:2.2em; margin-bottom:8px;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
h2 { font-size:1.5em; margin:30px 0 16px; color:var(--accent2);
  border-bottom:1px solid var(--border); padding-bottom:8px; }
.subtitle { color:var(--text2); margin-bottom:24px; font-size:1.05em; }
.meta-desc { color:var(--text); margin:8px 0 0; }
.stats-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
  gap:16px; margin:20px 0; }
.stat-card { background:var(--card); border:1px solid var(--border); border-radius:12px;
  padding:20px; text-align:center; }
.stat-card .number { font-size:2.4em; font-weight:700; }
.stat-card .label { color:var(--text2); font-size:0.9em; margin-top:4px; }
.stat-pass .number { color:var(--green); }
.stat-fail .number { color:var(--red); }
.stat-error .number { color:var(--orange); }
.stat-rate .number { color:var(--accent); }
.chart-container { background:var(--card); border:1px solid var(--border);
  border-radius:12px; padding:24px; margin:16px 0; }
.bar-chart { display:flex; flex-direction:column; gap:8px; }
.bar-row { display:flex; align-items:center; gap:12px; }
.bar-label { width:260px; text-align:right; font-size:0.85em; color:var(--text2);
  flex-shrink:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.bar-track { flex:1; height:28px; background:var(--card2); border-radius:6px; overflow:hidden; }
.bar-fill { height:100%; border-radius:6px; display:flex; align-items:center;
  padding-left:8px; font-size:0.8em; font-weight:600; color:white; min-width:34px; }
.bar-fill.green { background:linear-gradient(90deg,#2e7d32,#4caf50); }
.bar-fill.red { background:linear-gradient(90deg,#c62828,#ff5a65); }
.bar-fill.orange { background:linear-gradient(90deg,#e65100,#ffab40); }
.bar-fill.purple { background:linear-gradient(90deg,#4a148c,#b388ff); }
.bar-fill.blue { background:linear-gradient(90deg,#0d47a1,#4fc3f7); }
.bar-fill.yellow { background:linear-gradient(90deg,#f57f17,#ffd740); }
.bar-fill.pink { background:linear-gradient(90deg,#880e4f,#ff80ab); }
.category-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(380px,1fr));
  gap:16px; margin:16px 0; }
.category-card { background:var(--card); border:1px solid var(--border); border-radius:12px;
  padding:20px; border-left:4px solid var(--accent); }
.cat-title { font-size:1.1em; font-weight:600; margin-bottom:8px; display:flex;
  align-items:center; gap:8px; flex-wrap:wrap; }
.cat-count { background:var(--card2); padding:2px 10px; border-radius:12px;
  font-size:0.8em; }
.cat-tags { margin:6px 0 10px; display:flex; gap:6px; flex-wrap:wrap; }
.tag-chip { background:var(--card2); color:var(--accent2); padding:2px 8px;
  border-radius:10px; font-size:0.75em; font-family:monospace; }
.cat-desc { color:var(--text2); font-size:0.9em; margin-bottom:12px; }
.cat-suggestion { background:rgba(108,114,255,0.1); border-radius:8px; padding:10px 14px;
  font-size:0.88em; color:var(--accent2); }
.cat-suggestion strong { color:var(--accent); }
.badge { display:inline-block; padding:2px 10px; border-radius:10px; font-size:0.78em;
  font-weight:700; }
.comparison-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin:16px 0; }
.comp-card { background:var(--card); border:1px solid var(--border); border-radius:12px;
  padding:20px; }
.comp-card h4 { margin-bottom:12px; font-size:1em; }
.comp-row { display:flex; justify-content:space-between; padding:6px 0;
  border-bottom:1px solid var(--border); }
.comp-row:last-child { border-bottom:none; }
.comp-val { font-weight:600; }
.reason-block { background:var(--card); border:1px solid var(--border); border-radius:12px;
  padding:14px 18px; margin:12px 0; border-left:4px solid var(--accent2); }
.reason-block h3 { margin-bottom:6px; font-size:1.05em; }
.reason-block .rdesc { color:var(--text2); font-size:0.85em; margin-bottom:8px; }
.reason-block ul { padding-left:18px; }
.reason-block li { margin:3px 0; font-size:0.9em; }
table { width:100%; border-collapse:collapse; font-size:0.85em; }
th { background:var(--card2); color:var(--accent2); padding:10px 12px; text-align:left;
  font-weight:600; }
td { padding:8px 12px; border-bottom:1px solid var(--border); }
tr:hover td { background:rgba(108,114,255,0.05); }
.scroll-table { max-height:600px; overflow-y:auto; border-radius:12px;
  border:1px solid var(--border); }
.empty { color:var(--text2); font-style:italic; }
footer { color:var(--text2); font-size:0.8em; margin-top:30px; text-align:center; }
"""


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _stat_cards(stats: dict[str, Any]) -> str:
    pr = stats.get("pass_rate")
    pr_txt = f"{pr * 100:.1f}%" if isinstance(pr, (int, float)) else "—"
    cards = [
        ("stat-rate", pr_txt, "Pass rate"),
        ("", stats.get("total", "—"), "Total trials"),
        ("stat-pass", stats.get("passed", "—"), "Passed"),
        ("stat-fail", stats.get("failed", "—"), "Failed (reward=0)"),
        ("stat-error", stats.get("errors", "—"), "Errored"),
    ]
    items = "".join(
        f'<div class="stat-card {cls}"><div class="number">{_esc(num)}</div>'
        f'<div class="label">{_esc(lbl)}</div></div>'
        for cls, num, lbl in cards
    )
    return f'<div class="stats-grid">{items}</div>'


def _tag_bars(tag_rows: list[dict[str, Any]]) -> str:
    if not tag_rows:
        return '<div class="chart-container"><p class="empty">No tags assigned yet.</p></div>'
    top = max((r["count"] for r in tag_rows), default=1) or 1
    rows = []
    for i, r in enumerate(tag_rows):
        pct = max(6, round(r["count"] / top * 100))
        color = BAR_COLORS[i % len(BAR_COLORS)]
        label = _esc(r["tag"])
        rows.append(
            f'<div class="bar-row"><div class="bar-label" title="{_esc(r.get("description", ""))}">'
            f'{label}</div><div class="bar-track">'
            f'<div class="bar-fill {color}" style="width:{pct}%">{_esc(r["count"])}</div>'
            f'</div></div>'
        )
    return f'<div class="chart-container"><div class="bar-chart">{"".join(rows)}</div></div>'


def _action_cards(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return '<p class="empty">No action cards yet.</p>'
    ordered = sorted(
        cards,
        key=lambda c: (PRIORITY_ORDER.index(c.get("priority", "Medium"))
                       if c.get("priority") in PRIORITY_ORDER else 99),
    )
    out = []
    for c in ordered:
        prio = c.get("priority", "Medium")
        color = PRIORITY_COLORS.get(prio, "#6c72ff")
        tags = "".join(f'<span class="tag-chip">{_esc(t)}</span>'
                       for t in c.get("tags", []))
        tags_html = f'<div class="cat-tags">{tags}</div>' if tags else ""
        action = _esc(c.get("action", ""))
        action_html = (
            f'<div class="cat-suggestion"><strong>💡 How to address:</strong> {action}</div>'
            if action else ""
        )
        out.append(
            f'<div class="category-card" style="border-left-color:{color}">'
            f'<div class="cat-title"><span>{_esc(c.get("title", "Untitled"))}</span>'
            f'<span class="badge" style="background:{color}22;color:{color}">{_esc(prio)}</span>'
            f'</div>{tags_html}'
            f'<div class="cat-desc">{_esc(c.get("issue", ""))}</div>'
            f'{action_html}</div>'
        )
    return f'<div class="category-grid">{"".join(out)}</div>'


def _samples_table(samples: list[dict[str, Any]]) -> str:
    if not samples:
        return '<p class="empty">No tagged samples.</p>'
    body = "".join(
        f'<tr><td>{_esc(s["name"])}</td><td>{_esc(s.get("status", ""))}</td>'
        f'<td>{_esc(", ".join(s.get("tags", [])))}</td></tr>'
        for s in samples
    )
    return (
        '<div class="scroll-table"><table><thead><tr>'
        '<th>Sample</th><th>Status</th><th>Tags</th>'
        f'</tr></thead><tbody>{body}</tbody></table></div>'
    )


def _fmt(n: Any) -> str:
    if isinstance(n, (int, float)):
        return f"{n:,}"
    return "—"


def _compare_cards(compare: dict[str, Any] | None) -> str:
    if not compare:
        return ""
    p, f = compare.get("passed", {}), compare.get("failed", {})

    def card(title: str, color: str, d: dict[str, Any]) -> str:
        return (
            f'<div class="comp-card"><h4 style="color:{color}">{title} '
            f'({_esc(d.get("n", 0))})</h4>'
            f'<div class="comp-row"><span>Avg input tokens</span>'
            f'<span class="comp-val" style="color:{color}">{_fmt(d.get("avg_input"))}</span></div>'
            f'<div class="comp-row"><span>Avg output tokens</span>'
            f'<span class="comp-val" style="color:{color}">{_fmt(d.get("avg_output"))}</span></div>'
            f'<div class="comp-row"><span>Avg steps</span>'
            f'<span class="comp-val" style="color:{color}">{_fmt(d.get("avg_steps"))}</span></div>'
            f'</div>'
        )

    return (
        '<h2>📈 Passed vs failed (tokens & steps)</h2>'
        '<div class="comparison-grid">'
        f'{card("✅ Passed", "#4caf50", p)}{card("❌ Failed", "#ff5a65", f)}'
        '</div>'
    )


def _repo_bars(repos: list[dict[str, Any]] | None) -> str:
    if not repos:
        return ""
    rows = []
    for r in repos:
        total = r["total"] or 1
        rate = r["passed"] / total
        pct = round(rate * 100)
        color = "green" if rate >= 0.6 else ("orange" if rate >= 0.3 else "red")
        rows.append(
            f'<div class="bar-row"><div class="bar-label">{_esc(r["repo"])}</div>'
            f'<div class="bar-track"><div class="bar-fill {color}" '
            f'style="width:{max(6, pct)}%">{r["passed"]}/{r["total"]} ({pct}%)</div>'
            f'</div></div>'
        )
    return (
        '<h2>📦 Analysis by repository</h2>'
        f'<div class="chart-container"><div class="bar-chart">{"".join(rows)}</div></div>'
    )


def _failures_table(samples: list[dict[str, Any]], with_reason: bool = False) -> str:
    head = ("<tr><th>Sample</th>"
            + ("<th>Reason</th>" if with_reason else "")
            + "<th>Status</th><th>Steps</th><th>Input</th><th>Output</th><th>Note</th></tr>")
    body = ""
    for s in samples:
        reason = f"<td>{_esc(s.get('tag', ''))}</td>" if with_reason else ""
        body += (
            f"<tr><td>{_esc(s['name'])}</td>{reason}"
            f"<td>{_esc(s.get('status', ''))}</td>"
            f"<td>{_esc(s.get('steps'))}</td>"
            f"<td>{_fmt(s.get('input_tokens'))}</td>"
            f"<td>{_fmt(s.get('output_tokens'))}</td>"
            f"<td>{_esc(s.get('note', ''))}</td></tr>"
        )
    return f'<div class="scroll-table"><table><thead>{head}</thead><tbody>{body}</tbody></table></div>'


def _failures_by_reason(failures: list[dict[str, Any]] | None) -> str:
    if not failures:
        return ""
    all_rows = [{**s, "tag": g["tag"]} for g in failures for s in g["samples"]]
    parts = ['<h2>📋 Failed trials by reason</h2>']
    parts.append(f'<div class="reason-block"><h3>All '
                 f'<span class="cat-count">{len(all_rows)}</span></h3>'
                 f'{_failures_table(all_rows, with_reason=True)}</div>')
    for grp in failures:
        desc = (f'<div class="rdesc">{_esc(grp["description"])}</div>'
                if grp.get("description") else "")
        parts.append(
            f'<div class="reason-block"><h3>{_esc(grp["tag"])} '
            f'<span class="cat-count">{len(grp["samples"])}</span></h3>'
            f'{desc}{_failures_table(grp["samples"])}</div>'
        )
    return "".join(parts)


def build_report_html(
    meta: dict[str, Any],
    stats: dict[str, Any],
    tag_rows: list[dict[str, Any]],
    cards: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    compare: dict[str, Any] | None = None,
    repos: list[dict[str, Any]] | None = None,
    failures_by_reason: list[dict[str, Any]] | None = None,
) -> str:
    title = meta.get("experiment_name") or "Trajectory Failure Analysis"
    subtitle_bits = []
    if stats.get("total") is not None:
        subtitle_bits.append(f"{stats['total']} trials")
    if meta.get("source_path"):
        subtitle_bits.append(f"source: {meta['source_path']}")
    if meta.get("model"):
        subtitle_bits.append(f"model: {meta['model']}")
    if meta.get("exported_at"):
        subtitle_bits.append(meta["exported_at"])
    subtitle = "  |  ".join(_esc(b) for b in subtitle_bits)
    desc = (f'<p class="meta-desc">{_esc(meta["description"])}</p>'
            if meta.get("description") else "")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
<style>{_CSS}</style></head>
<body><div class="container">
<h1>🔬 {_esc(title)}</h1>
<p class="subtitle">{subtitle}</p>
{desc}

<h2>📊 Overview</h2>
{_stat_cards(stats)}

<h2>🏷️ Failure categories by tag</h2>
{_tag_bars(tag_rows)}

{_compare_cards(compare)}

{_repo_bars(repos)}

{_failures_by_reason(failures_by_reason)}

<h2>🛠️ Action items</h2>
{_action_cards(cards)}

<h2>📦 Tagged samples</h2>
{_samples_table(samples)}

<footer>Generated by Trajectory Analyzer</footer>
</div></body></html>"""
