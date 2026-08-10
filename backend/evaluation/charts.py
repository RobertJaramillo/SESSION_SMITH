"""
evaluation/charts.py — Render the ExperimentReport as a visual dashboard.

Produces a SINGLE self-contained `report.html` (inline SVG + CSS, no JS libraries,
no Python plotting dependency) that opens in any browser and in the IDE preview.
It complements report.md/json — same numbers, shown as charts.

Design follows the data-viz method:
• Two systems = two CATEGORICAL series → blue (slot 1) + orange (slot 2), the
validated default palette (checks pass light & dark).
• One axis per chart. The fact-grounded metrics mix rates (0–1) and error counts,
so they get SEPARATE charts rather than a forbidden dual axis.
• Grouped bars for magnitude comparison; a legend is always present for 2 series,
and every bar is direct-labeled (identity never by color alone).
• Error bars show ± std across runs (reviewer refinement #3: variance matters).
• Light/dark themes, a theme toggle, and a table view (accessibility fallback).

The chart-building helpers take plain numbers, so nothing here depends on the rest
of the pipeline beyond the ExperimentReport it is handed.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from .rubric import FACT_METRIC_HIGHER_IS_BETTER
from .schemas import ExperimentReport, MeanStd, SystemLabel

# Series colors: slot 1 (blue) = our system, slot 2 (orange) = baseline. Dark
# steps are the same hues re-stepped for the dark surface (see palette.md).
SERIES = [
    (SystemLabel.our_system, "Our System", "var(--series-1)"),
    (SystemLabel.baseline_chatgpt, "Baseline (ChatGPT)", "var(--series-2)"),
]


# =============================================================================
# Low-level SVG grouped-bar builder
# =============================================================================

def _grouped_bar_svg(
    groups: list[str],
    series_values: list[list[MeanStd]],   # series_values[series_idx][group_idx]
    series_colors: list[str],
    *,
    ymax: float,
    value_fmt: str = "{:.2f}",
    y_ticks: int = 5,
) -> str:
    """Return an <svg> grouped-bar chart. One axis, baseline-anchored bars with
    4px rounded tops, a 2px surface gap between adjacent bars, direct value labels,
    ± std whiskers, recessive gridlines, and a native hover tooltip per bar."""
    W, H = 640, 320
    ml, mr, mt, mb = 44, 16, 28, 64          # margins (mb roomy for wrapped labels)
    plot_w, plot_h = W - ml - mr, H - mt - mb
    n_groups = len(groups)
    n_series = len(series_values)

    group_w = plot_w / n_groups
    gap = 2                                    # surface gap between adjacent bars
    bar_w = max(6, (group_w * 0.62 - gap * (n_series - 1)) / n_series)

    def y_of(v: float) -> float:
        return mt + plot_h * (1 - (v / ymax if ymax else 0))

    parts: list[str] = [
        f'<svg viewBox="0 0 {W} {H}" role="img" '
        f'preserveAspectRatio="xMidYMid meet" class="chart-svg">'
    ]

    # --- gridlines + y ticks (recessive) ---------------------------------
    for t in range(y_ticks + 1):
        v = ymax * t / y_ticks
        y = y_of(v)
        parts.append(
            f'<line x1="{ml}" y1="{y:.1f}" x2="{W - mr}" y2="{y:.1f}" '
            f'class="grid" />'
        )
        parts.append(
            f'<text x="{ml - 6}" y="{y + 3:.1f}" class="tick" '
            f'text-anchor="end">{value_fmt.format(v)}</text>'
        )

    # --- bars -------------------------------------------------------------
    for gi, group in enumerate(groups):
        group_x = ml + group_w * gi
        cluster_w = bar_w * n_series + gap * (n_series - 1)
        start_x = group_x + (group_w - cluster_w) / 2
        for si in range(n_series):
            ms = series_values[si][gi]
            x = start_x + si * (bar_w + gap)
            y = y_of(ms.mean)
            h = (mt + plot_h) - y
            tip = f"{groups[gi]} — {series_values[si][gi].mean:.3f} (n={ms.n})"
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                f'height="{max(0, h):.1f}" rx="4" fill="{series_colors[si]}" '
                f'class="bar"><title>{escape(tip)}</title></rect>'
            )
            # ± std whisker
            if ms.std > 0:
                cx = x + bar_w / 2
                y_hi, y_lo = y_of(ms.mean + ms.std), y_of(ms.mean - ms.std)
                parts.append(
                    f'<line x1="{cx:.1f}" y1="{y_hi:.1f}" x2="{cx:.1f}" '
                    f'y2="{y_lo:.1f}" class="whisker" />'
                    f'<line x1="{cx-3:.1f}" y1="{y_hi:.1f}" x2="{cx+3:.1f}" '
                    f'y2="{y_hi:.1f}" class="whisker" />'
                    f'<line x1="{cx-3:.1f}" y1="{y_lo:.1f}" x2="{cx+3:.1f}" '
                    f'y2="{y_lo:.1f}" class="whisker" />'
                )
            # direct value label
            parts.append(
                f'<text x="{x + bar_w/2:.1f}" y="{y - 5:.1f}" class="val" '
                f'text-anchor="middle">{value_fmt.format(ms.mean)}</text>'
            )

        # x label (wrapped to 2 lines on the space)
        label_y = mt + plot_h + 16
        words = group.split()
        mid = (len(words) + 1) // 2
        line1, line2 = " ".join(words[:mid]), " ".join(words[mid:])
        cx = group_x + group_w / 2
        parts.append(f'<text x="{cx:.1f}" y="{label_y:.1f}" class="axlabel" text-anchor="middle">{escape(line1)}</text>')
        if line2:
            parts.append(f'<text x="{cx:.1f}" y="{label_y + 13:.1f}" class="axlabel" text-anchor="middle">{escape(line2)}</text>')

    # baseline
    parts.append(
        f'<line x1="{ml}" y1="{mt + plot_h}" x2="{W - mr}" y2="{mt + plot_h}" '
        f'class="baseline" />'
    )
    parts.append("</svg>")
    return "".join(parts)


# =============================================================================
# Report-level helpers
# =============================================================================

def _agg_by_system(report: ExperimentReport) -> dict[SystemLabel, "object"]:
    return {a.system_label: a for a in report.system_aggregates}


def _legend() -> str:
    items = "".join(
        f'<span class="leg"><span class="swatch" style="background:{color}"></span>{escape(name)}</span>'
        for _, name, color in SERIES
    )
    return f'<div class="legend">{items}</div>'


def _figure(title: str, subtitle: str, svg: str, *, legend: bool = True) -> str:
    leg = _legend() if legend else ""
    return (
        f'<figure class="card">'
        f'<figcaption><h3>{escape(title)}</h3>'
        f'<p class="sub">{escape(subtitle)}</p></figcaption>'
        f'{leg}{svg}</figure>'
    )


def _series_values(report: ExperimentReport, keys: list[str], kind: str) -> list[list[MeanStd]]:
    """Build series_values[series_idx][group_idx] for the given metric keys."""
    aggs = _agg_by_system(report)
    out: list[list[MeanStd]] = []
    for label, _, _ in SERIES:
        agg = aggs.get(label)
        row: list[MeanStd] = []
        for k in keys:
            stats = (agg.criterion_stats if kind == "criterion" else agg.fact_stats) if agg else {}
            row.append(stats.get(k, MeanStd()))
        out.append(row)
    return out


# =============================================================================
# KPI tiles (headline numbers for our system, with delta vs baseline)
# =============================================================================

def _kpi_row(report: ExperimentReport) -> str:
    aggs = _agg_by_system(report)
    ours = aggs.get(SystemLabel.our_system)
    base = aggs.get(SystemLabel.baseline_chatgpt)
    if not (ours and base):
        return ""

    def qual_avg(a) -> float:
        vals = [ms.mean for ms in a.criterion_stats.values() if ms.n]
        return sum(vals) / len(vals) if vals else 0.0

    tiles = []

    def tile(label: str, ours_v: float, base_v: float, higher_better: bool, fmt: str):
        delta = ours_v - base_v
        improved = (delta > 0) if higher_better else (delta < 0)
        cls = "good" if improved else ("bad" if delta != 0 else "flat")
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "■")
        word = "better" if improved else ("worse" if delta != 0 else "same")
        tiles.append(
            f'<div class="kpi"><div class="kpi-label">{escape(label)}</div>'
            f'<div class="kpi-val">{fmt.format(ours_v)}</div>'
            f'<div class="kpi-delta {cls}">{arrow} {fmt.format(abs(delta))} vs baseline '
            f'<span class="kpi-word">({word})</span></div></div>'
        )

    tile("Rubric avg (1–5)", qual_avg(ours), qual_avg(base), True, "{:.2f}")
    tile("Facts preserved", ours.fact_stats["preservation_rate"].mean,
         base.fact_stats["preservation_rate"].mean, True, "{:.0%}")
    tile("Contradictions", ours.fact_stats["contradictions"].mean,
         base.fact_stats["contradictions"].mean, False, "{:.1f}")
    # Creative additions is deliberately NOT a KPI tile here: it's informational
    # (see rubric.FACT_METRIC_HIGHER_IS_BETTER), not a "better/worse vs baseline"
    # comparison — see the fact-grounded metrics table in the markdown report.

    return f'<div class="kpi-row">{"".join(tiles)}</div>'


# =============================================================================
# Assemble the page
# =============================================================================

def render_html(report: ExperimentReport) -> str:
    rubric_keys = [c.key for c in report.rubric]
    rubric_names = [c.name for c in report.rubric]

    # Fact metrics split by scale: rates (0–1) vs error counts (0..max).
    rate_keys = [k for k, hb in FACT_METRIC_HIGHER_IS_BETTER.items() if hb]      # preservation, rel_acc
    count_keys = [k for k, hb in FACT_METRIC_HIGHER_IS_BETTER.items() if not hb]  # contradictions

    # ymax for counts = ceil of the largest count seen (min 1).
    count_vals = _series_values(report, count_keys, "fact")
    max_count = max((ms.mean + ms.std for row in count_vals for ms in row), default=1.0)
    count_ymax = max(1.0, round(max_count + 0.5))

    # --- charts ----------------------------------------------------------
    rubric_chart = _figure(
        "Qualitative rubric",
        "Mean score across runs (1–5, higher is better). Whiskers = ± std.",
        _grouped_bar_svg(rubric_names, _series_values(report, rubric_keys, "criterion"),
                         [c for _, _, c in SERIES], ymax=5, value_fmt="{:.1f}"),
    )
    rates_chart = _figure(
        "Fact preservation & relationship accuracy",
        "Fraction checked against the original notes (higher is better).",
        _grouped_bar_svg([k.replace("_", " ") for k in rate_keys],
                         _series_values(report, rate_keys, "fact"),
                         [c for _, _, c in SERIES], ymax=1.0, value_fmt="{:.0%}"),
    )
    counts_chart = _figure(
        "Errors introduced (lower is better)",
        "Counts of contradictions vs the notes.",
        _grouped_bar_svg([k.replace("_", " ") for k in count_keys],
                         count_vals, [c for _, _, c in SERIES],
                         ymax=count_ymax, value_fmt="{:.1f}"),
    )

    # Agreement: single series (kappa per criterion) — sequential blue, no legend.
    ag = report.agreement
    agreement_chart = ""
    if ag and any(v is not None for v in ag.per_criterion_kappa.values()):
        ak_names = [report_rubric_name(report, k) for k in ag.per_criterion_kappa]
        ak_vals = [[MeanStd(mean=(v if v is not None else 0.0), n=1)
                    for v in ag.per_criterion_kappa.values()]]
        agreement_chart = _figure(
            "Inter-evaluator agreement",
            f"Quadratic-weighted Cohen's κ per criterion (1.0 = perfect). {escape(ag.summary)}",
            _grouped_bar_svg(ak_names, ak_vals, ["var(--series-1)"], ymax=1.0, value_fmt="{:.2f}"),
            legend=False,
        )

    # --- per-document table (accessibility fallback / detail) ------------
    table = _document_table(report)

    kpis = _kpi_row(report)
    disagreements = _disagreements_html(report)

    return _PAGE.format(
        campaign=escape(report.campaign_id),
        n_runs=report.n_runs_per_system,
        evaluators=escape(", ".join(report.evaluator_ids)),
        kpis=kpis,
        rubric_chart=rubric_chart,
        rates_chart=rates_chart,
        counts_chart=counts_chart,
        agreement_chart=agreement_chart,
        disagreements=disagreements,
        table=table,
        conclusion=escape(report.conclusion).replace("\n", "<br>"),
    )


def report_rubric_name(report: ExperimentReport, key: str) -> str:
    for c in report.rubric:
        if c.key == key:
            return c.name
    return key


def _document_table(report: ExperimentReport) -> str:
    head = ["Blind ID", "System", "Run"] + [c.name for c in report.rubric] + \
           ["Preserved", "Creative additions", "Contradictions", "Rel. acc"]
    rows = []
    for dr in sorted(report.document_results, key=lambda d: d.blind_id):
        sysname = "Our System" if dr.system_label == SystemLabel.our_system else "Baseline"
        cells = [dr.blind_id, sysname, str(dr.run_index)]
        cells += [f"{dr.mean_criterion_scores.get(c.key, float('nan')):.1f}" for c in report.rubric]
        fm = dr.mean_fact_metrics
        cells += [f"{fm.get('preservation_rate', 0):.2f}", f"{fm.get('creative_additions', 0):.1f}",
                  f"{fm.get('contradictions', 0):.1f}", f"{fm.get('relationship_accuracy', 0):.2f}"]
        rows.append("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in cells) + "</tr>")
    thead = "<tr>" + "".join(f"<th>{escape(h)}</th>" for h in head) + "</tr>"
    return f'<table class="dtable"><thead>{thead}</thead><tbody>{"".join(rows)}</tbody></table>'


def _disagreements_html(report: ExperimentReport) -> str:
    ag = report.agreement
    if not ag or not ag.disagreements:
        return '<p class="muted">No evaluator disagreements exceeded the threshold.</p>'
    items = []
    for d in ag.disagreements:
        sysname = ""
        if d.system_label:
            sysname = " · " + ("Our System" if d.system_label == SystemLabel.our_system else "Baseline")
        crit = report_rubric_name(report, d.criterion_key)
        scores = ", ".join(f"{k}={v}" for k, v in d.scores_by_evaluator.items())
        items.append(
            f'<details class="disagreement"><summary><b>{escape(d.blind_id)}{escape(sysname)}</b> · '
            f'{escape(crit)} <span class="chip">spread {d.spread}: {escape(scores)}</span></summary>'
            f'<p>{escape(d.discussion)}</p></details>'
        )
    return "".join(items)


# =============================================================================
# Page shell (CSS = palette custom properties + light/dark; tiny theme-toggle JS)
# =============================================================================

_PAGE = """\
<!doctype html>
<html lang="en" data-theme="">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evaluation Report — {campaign}</title>
<style>
  :root {{
    color-scheme: light;
    --page:#f9f9f7; --surface-1:#fcfcfb; --text-primary:#0b0b0b; --text-secondary:#52514e;
    --muted:#898781; --grid:#e1e0d9; --baseline:#c3c2b7; --border:rgba(11,11,11,0.10);
    --series-1:#2a78d6; --series-2:#eb6834;
    --good:#0ca30c; --bad:#d03b3b;
  }}
  html[data-theme="dark"] {{
    color-scheme: dark;
    --page:#0d0d0d; --surface-1:#1a1a19; --text-primary:#fff; --text-secondary:#c3c2b7;
    --muted:#898781; --grid:#2c2c2a; --baseline:#383835; --border:rgba(255,255,255,0.10);
    --series-1:#3987e5; --series-2:#d95926; --good:#0ca30c; --bad:#d03b3b;
  }}
  @media (prefers-color-scheme: dark) {{
    html:not([data-theme="light"]) {{
      color-scheme: dark;
      --page:#0d0d0d; --surface-1:#1a1a19; --text-primary:#fff; --text-secondary:#c3c2b7;
      --grid:#2c2c2a; --baseline:#383835; --border:rgba(255,255,255,0.10);
      --series-1:#3987e5; --series-2:#d95926;
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--page); color:var(--text-primary);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.5; }}
  .wrap {{ max-width:980px; margin:0 auto; padding:32px 20px 80px; }}
  header {{ display:flex; align-items:baseline; justify-content:space-between; gap:16px; flex-wrap:wrap; }}
  h1 {{ font-size:24px; margin:0 0 4px; }}
  h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted);
    margin:40px 0 12px; }}
  h3 {{ font-size:16px; margin:0; }}
  .meta {{ color:var(--text-secondary); font-size:14px; }}
  .sub {{ color:var(--text-secondary); font-size:13px; margin:2px 0 8px; }}
  .muted {{ color:var(--muted); }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  @media (max-width:720px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
  .card {{ background:var(--surface-1); border:1px solid var(--border); border-radius:12px;
    margin:0; padding:16px; }}
  .chart-svg {{ width:100%; height:auto; display:block; }}
  .grid {{ stroke:var(--grid); stroke-width:1; }}
  .baseline {{ stroke:var(--baseline); stroke-width:1.5; }}
  .whisker {{ stroke:var(--text-secondary); stroke-width:1.5; }}
  .bar {{ transition:opacity .12s; }} .bar:hover {{ opacity:.82; }}
  .tick, .axlabel {{ fill:var(--muted); font-size:11px; font-variant-numeric:tabular-nums; }}
  .val {{ fill:var(--text-primary); font-size:11px; font-weight:600; font-variant-numeric:tabular-nums; }}
  .legend {{ display:flex; gap:16px; margin:2px 0 10px; font-size:13px; color:var(--text-secondary); }}
  .leg {{ display:inline-flex; align-items:center; gap:6px; }}
  .swatch {{ width:12px; height:12px; border-radius:3px; display:inline-block; }}
  .kpi-row {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:20px 0 8px; }}
  @media (max-width:720px) {{ .kpi-row {{ grid-template-columns:repeat(2,1fr); }} }}
  .kpi {{ background:var(--surface-1); border:1px solid var(--border); border-radius:12px; padding:14px; }}
  .kpi-label {{ font-size:12px; color:var(--muted); }}
  .kpi-val {{ font-size:30px; font-weight:700; margin:2px 0; font-variant-numeric:tabular-nums; }}
  .kpi-delta {{ font-size:12px; }}
  .kpi-delta.good {{ color:var(--good); }} .kpi-delta.bad {{ color:var(--bad); }}
  .kpi-delta.flat {{ color:var(--muted); }}
  .kpi-word {{ color:var(--muted); }}
  table.dtable {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:8px; }}
  .dtable th, .dtable td {{ text-align:right; padding:6px 8px; border-bottom:1px solid var(--grid);
    font-variant-numeric:tabular-nums; }}
  .dtable th:first-child, .dtable td:first-child,
  .dtable th:nth-child(2), .dtable td:nth-child(2) {{ text-align:left; }}
  .dtable thead th {{ color:var(--muted); font-weight:600; border-bottom:1.5px solid var(--baseline); }}
  details.disagreement {{ background:var(--surface-1); border:1px solid var(--border);
    border-radius:10px; padding:10px 14px; margin:8px 0; }}
  details.disagreement summary {{ cursor:pointer; }}
  .chip {{ font-size:11px; color:var(--text-secondary); background:var(--grid);
    border-radius:20px; padding:2px 8px; margin-left:6px; }}
  .toggle {{ font:inherit; font-size:13px; cursor:pointer; background:var(--surface-1);
    color:var(--text-primary); border:1px solid var(--border); border-radius:8px; padding:6px 12px; }}
  .conclusion {{ background:var(--surface-1); border:1px solid var(--border); border-radius:12px;
    padding:16px; font-size:14px; }}
  footer {{ margin-top:40px; color:var(--muted); font-size:12px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>Evaluation Report</h1>
      <div class="meta">Campaign <b>{campaign}</b> · {n_runs} run(s) per system · evaluators: {evaluators}</div>
    </div>
    <button class="toggle" onclick="toggleTheme()">Toggle light / dark</button>
  </header>

  {kpis}

  <h2>System comparison</h2>
  <div class="grid2">
    {rubric_chart}
    {rates_chart}
    {counts_chart}
    {agreement_chart}
  </div>

  <h2>Evaluator disagreements (deep dive)</h2>
  {disagreements}

  <h2>Per-document scores (blind)</h2>
  <div class="card">{table}</div>

  <h2>Conclusion</h2>
  <div class="conclusion">{conclusion}</div>

  <footer>Generated by backend/evaluation. Charts use a CVD-validated palette;
  identity is shown by legend + direct labels, not color alone. A table view is
  included above for accessibility.</footer>
</div>
<script>
  function toggleTheme() {{
    var el = document.documentElement;
    var now = el.getAttribute('data-theme');
    var next = now === 'dark' ? 'light'
             : now === 'light' ? 'dark'
             : (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'light' : 'dark');
    el.setAttribute('data-theme', next);
  }}
</script>
</body>
</html>
"""


def save_html(report: ExperimentReport, out_dir: str | Path) -> Path:
    """Write report.html into out_dir and return its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "report.html"
    path.write_text(render_html(report))
    return path


__all__ = ["render_html", "save_html"]
