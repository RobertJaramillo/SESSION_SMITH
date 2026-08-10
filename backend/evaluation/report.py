"""
evaluation/report.py — Turn an ExperimentReport into readable output.

Produces two artifacts side by side:
  • report.json — the full ExperimentReport (machine-readable, replayable).
  • report.md   — a human-readable write-up for the professor / the team.

The markdown is structured to answer, in order, everything the evaluation thread
asked for: the documented generator settings, the blind per-document scores, the
inter-evaluator agreement + disagreement discussions, and the system comparison
with a conclusion.
"""

from __future__ import annotations

import json
from pathlib import Path

from .rubric import FACT_GROUNDED_CRITERIA, FACT_METRIC_HIGHER_IS_BETTER, RUBRIC_BY_KEY
from .schemas import ExperimentReport, MeanStd, SystemLabel


def _fmt(ms: MeanStd) -> str:
    return f"{ms.mean:.2f} ± {ms.std:.2f} (n={ms.n})"


def _system_name(label: SystemLabel) -> str:
    return {
        SystemLabel.our_system: "Our System",
        SystemLabel.baseline_chatgpt: "Baseline (ChatGPT)",
    }.get(label, str(label))


def render_markdown(report: ExperimentReport) -> str:
    L: list[str] = []
    w = L.append

    w(f"# Evaluation Report — {report.campaign_id}")
    w("")
    w(f"- **Runs per system:** {report.n_runs_per_system}")
    w(f"- **Evaluators:** {', '.join(report.evaluator_ids)}")
    if report.gold_reference:
        n_facts = len(report.gold_reference.facts)
        n_rel = len(report.gold_reference.relationship_facts)
        w(f"- **Gold reference:** {n_facts} facts ({n_rel} relationships) extracted from the session notes")
    w("")
    w("> **Scope note:** the fact-grounded metrics below score faithfulness to "
      "session notes. The platform's World Builder (`build_world()`) is a "
      "deliberately creative co-author (see `docs/AI_ARCHITECTURE.md` §6) and its "
      "output is excluded from this comparison by design — score a "
      "`?scope=session_notes` world-export, not `?scope=all`, when the candidate "
      "is a real product export (see `backend/evaluation/README.md`).")
    w("")

    # --- Methodology / reproducibility ------------------------------------
    w("## 1. Generation settings (reproducibility)")
    w("")
    w("Both systems consumed the *same* session notes. Settings are recorded so "
      "the experiment can be reproduced despite run-to-run LLM variation.")
    w("")
    for cfg in report.generator_configs:
        w(f"### {_system_name(cfg.system_label)}")
        w(f"- provider / model: `{cfg.provider}` / `{cfg.model_name}`")
        w(f"- prompt version: `{cfg.prompt_version}`")
        w(f"- temperature: {cfg.temperature}"
          + (f", top_p: {cfg.top_p}" if cfg.top_p is not None else "")
          + (f", seed: {cfg.seed}" if cfg.seed is not None else ""))
        if cfg.notes:
            w(f"- notes: {cfg.notes}")
        w("")
        w("<details><summary>Prompt template</summary>")
        w("")
        w("```text")
        w(cfg.prompt_text.strip())
        w("```")
        w("</details>")
        w("")

    # --- System comparison (the headline) ---------------------------------
    w("## 2. System comparison (mean ± std across runs)")
    w("")
    w("### Qualitative rubric (1–5, higher is better)")
    w("")
    header = ["Criterion"] + [_system_name(a.system_label) for a in report.system_aggregates]
    w("| " + " | ".join(header) + " |")
    w("| " + " | ".join(["---"] * len(header)) + " |")
    for crit in report.rubric:
        row = [crit.name]
        for agg in report.system_aggregates:
            ms = agg.criterion_stats.get(crit.key)
            row.append(_fmt(ms) if ms else "—")
        w("| " + " | ".join(row) + " |")
    w("")

    w("### Fact-grounded metrics (checked against the notes)")
    w("")
    for name, desc in FACT_GROUNDED_CRITERIA.items():
        if name in FACT_METRIC_HIGHER_IS_BETTER:
            arrow = "↑ better" if FACT_METRIC_HIGHER_IS_BETTER[name] else "↓ better"
        else:
            arrow = "informational, not scored"
        w(f"- **{name}** ({arrow}): {desc}")
    w("")
    header = ["Metric"] + [_system_name(a.system_label) for a in report.system_aggregates]
    w("| " + " | ".join(header) + " |")
    w("| " + " | ".join(["---"] * len(header)) + " |")
    for name in FACT_GROUNDED_CRITERIA:
        row = [name]
        for agg in report.system_aggregates:
            ms = agg.fact_stats.get(name)
            row.append(_fmt(ms) if ms else "—")
        w("| " + " | ".join(row) + " |")
    w("")

    # --- Inter-evaluator agreement ----------------------------------------
    w("## 3. Inter-evaluator agreement")
    w("")
    if report.agreement:
        ag = report.agreement
        w(ag.summary)
        w("")
        w("| Criterion | Quadratic-weighted κ | Exact agreement | Within-1 agreement |")
        w("| --- | --- | --- | --- |")
        for key, kappa in ag.per_criterion_kappa.items():
            name = RUBRIC_BY_KEY[key].name if key in RUBRIC_BY_KEY else key
            k = f"{kappa:.2f}" if kappa is not None else "n/a"
            ex = f"{ag.per_criterion_exact_rate.get(key, 0.0) * 100:.0f}%"
            adj = f"{ag.per_criterion_adjacent_rate.get(key, 0.0) * 100:.0f}%"
            w(f"| {name} | {k} | {ex} | {adj} |")
        w("")

        # --- Disagreement deep-dives --------------------------------------
        w("### 3.1 Disagreements (deep dive)")
        w("")
        if not ag.disagreements:
            w("_No (document, criterion) pair exceeded the disagreement threshold._")
        else:
            for i, d in enumerate(ag.disagreements, 1):
                crit_name = RUBRIC_BY_KEY[d.criterion_key].name if d.criterion_key in RUBRIC_BY_KEY else d.criterion_key
                sys = f" — {_system_name(d.system_label)}" if d.system_label else ""
                scores = ", ".join(f"{k}={v}" for k, v in d.scores_by_evaluator.items())
                w(f"**{i}. {d.blind_id}{sys} · {crit_name}** (spread {d.spread}: {scores})")
                w("")
                w(d.discussion)
                w("")
    else:
        w("_Only one evaluator — agreement not computed._")
    w("")

    # --- Per-document detail ----------------------------------------------
    w("## 4. Per-document scores (blind)")
    w("")
    w("Scores below are the mean across evaluators. `blind_id` is what the judges "
      "actually saw; the system column is revealed only after scoring.")
    w("")
    w("| Blind ID | System | Run | " + " | ".join(RUBRIC_BY_KEY[c.key].name for c in report.rubric) + " | preserved | creative additions | contradictions | rel.acc |")
    w("| --- | --- | --- | " + " | ".join(["---"] * (len(report.rubric) + 4)) + " |")
    for dr in sorted(report.document_results, key=lambda d: d.blind_id):
        crit_cells = [f"{dr.mean_criterion_scores.get(c.key, float('nan')):.1f}" for c in report.rubric]
        fm = dr.mean_fact_metrics
        w(
            f"| {dr.blind_id} | {_system_name(dr.system_label)} | {dr.run_index} | "
            + " | ".join(crit_cells)
            + f" | {fm.get('preservation_rate', 0):.2f}"
            + f" | {fm.get('creative_additions', 0):.1f}"
            + f" | {fm.get('contradictions', 0):.1f}"
            + f" | {fm.get('relationship_accuracy', 0):.2f} |"
        )
    w("")

    # --- Conclusion --------------------------------------------------------
    w("## 5. Conclusion")
    w("")
    w(report.conclusion or "_(no conclusion generated)_")
    w("")

    return "\n".join(L)


def build_conclusion(report: ExperimentReport) -> str:
    """A short, mechanical verdict comparing the two systems on the key metrics.
    Deterministic (no LLM) so the headline claim is defensible and reproducible."""
    aggs = {a.system_label: a for a in report.system_aggregates}
    ours = aggs.get(SystemLabel.our_system)
    base = aggs.get(SystemLabel.baseline_chatgpt)
    if not (ours and base):
        return "Both systems are required for a comparison; only one was evaluated."

    lines: list[str] = []
    # Qualitative: average across criteria.
    def avg_qual(a):
        vals = [ms.mean for ms in a.criterion_stats.values() if ms.n]
        return sum(vals) / len(vals) if vals else 0.0

    ours_q, base_q = avg_qual(ours), avg_qual(base)
    winner = "Our system" if ours_q > base_q else ("Baseline" if base_q > ours_q else "Tie")
    lines.append(
        f"Averaged over the qualitative rubric, our system scored {ours_q:.2f} vs "
        f"the baseline's {base_q:.2f} (1–5). Qualitative winner: **{winner}**."
    )

    # Fact-grounded, metric by metric, respecting direction.
    for name, higher_better in FACT_METRIC_HIGHER_IS_BETTER.items():
        o = ours.fact_stats.get(name)
        b = base.fact_stats.get(name)
        if not (o and b):
            continue
        better = (o.mean > b.mean) if higher_better else (o.mean < b.mean)
        who = "our system" if better else "the baseline" if o.mean != b.mean else "neither (tie)"
        lines.append(
            f"- {name}: ours {o.mean:.2f} vs baseline {b.mean:.2f} → favors {who}."
        )

    lines.append(
        "\nThese are automated results over a small sample; the numbers should be "
        "read together with the disagreement discussions in §3.1 and, ideally, a "
        "human spot-check of the flagged cases."
    )
    return "\n".join(lines)


def save_report(report: ExperimentReport, out_dir: str | Path) -> tuple[Path, Path, Path]:
    """Write report.json + report.md + report.html into out_dir.
    Returns (json_path, md_path, html_path)."""
    # Imported here to avoid a hard import cycle at module load.
    from .charts import save_html

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "report.json"
    md_path = out / "report.md"
    json_path.write_text(report.model_dump_json(indent=2))
    md_path.write_text(render_markdown(report))
    html_path = save_html(report, out)
    return json_path, md_path, html_path


__all__ = ["render_markdown", "build_conclusion", "save_report"]
