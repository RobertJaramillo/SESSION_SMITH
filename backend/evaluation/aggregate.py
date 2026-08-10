"""
evaluation/aggregate.py — Roll individual scorecards up into results.

Two levels of aggregation:

1. PER DOCUMENT (across evaluators)  -> DocumentResult Average the evaluators' 1–5 scores and their fact-grounded metrics into a consensus for each document, while keeping the raw scorecards attached so nothing is hidden.

2. PER SYSTEM (across repeated runs) -> SystemAggregate Because a single generation isn't trustworthy, we report mean ± std across the N runs of each system, for every criterion and every fact metric.

Pure standard library — statistics.mean / pstdev — no numpy.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean, pstdev

from .blinding import BlindingKey
from .rubric import DEFAULT_RUBRIC, FACT_GROUNDED_CRITERIA
from .schemas import (
    DocumentResult,
    EvaluatorScorecard,
    FactGroundedMetrics,
    MeanStd,
    RubricCriterion,
    SystemAggregate,
    SystemLabel,
)


# Fact metrics we surface in the aggregate (name -> how to read it off a scorecard).
def _fact_metric_values(fm: FactGroundedMetrics) -> dict[str, float]:
    """Flatten a FactGroundedMetrics into the scalar values we aggregate/report."""
    return {
        "preservation_rate": fm.preservation_rate,
        "relationship_accuracy": fm.relationship_accuracy,
        "creative_additions": float(fm.creative_additions),
        "contradictions": float(fm.contradictions),
    }


# =============================================================================
# Level 1 — per document, across evaluators
# =============================================================================

def build_document_result(
    blind_id: str,
    scorecards: list[EvaluatorScorecard],
    key: BlindingKey,
    rubric: list[RubricCriterion] | None = None,
) -> DocumentResult:
    """Merge every evaluator's scorecard for one document into a consensus.
    `key` un-blinds the true system identity for reporting AFTER scoring."""
    rubric = rubric or DEFAULT_RUBRIC
    doc = key.reveal(blind_id)

    mean_criterion: dict[str, float] = {}
    for crit in rubric:
        scores = [sc.score_for(crit.key) for sc in scorecards]
        scores = [s for s in scores if s is not None]
        if scores:
            mean_criterion[crit.key] = mean(scores)

    # Average each fact metric across evaluators.
    metric_accum: dict[str, list[float]] = defaultdict(list)
    for sc in scorecards:
        for name, val in _fact_metric_values(sc.fact_metrics).items():
            metric_accum[name].append(val)
    mean_fact = {name: mean(vals) for name, vals in metric_accum.items() if vals}

    return DocumentResult(
        doc_id=doc.doc_id,
        blind_id=blind_id,
        system_label=doc.system_label,
        run_index=doc.run_index,
        mean_criterion_scores=mean_criterion,
        mean_fact_metrics=mean_fact,
        scorecards=scorecards,
    )


# =============================================================================
# Level 2 — per system, across runs
# =============================================================================

def _mean_std(values: list[float]) -> MeanStd:
    if not values:
        return MeanStd(mean=0.0, std=0.0, n=0)
    return MeanStd(
        mean=mean(values),
        std=pstdev(values) if len(values) > 1 else 0.0,
        n=len(values),
    )


def build_system_aggregates(
    document_results: list[DocumentResult],
    rubric: list[RubricCriterion] | None = None,
) -> list[SystemAggregate]:
    """Group DocumentResults by system and compute mean ± std over the runs."""
    rubric = rubric or DEFAULT_RUBRIC
    by_system: dict[SystemLabel, list[DocumentResult]] = defaultdict(list)
    for dr in document_results:
        by_system[dr.system_label].append(dr)

    aggregates: list[SystemAggregate] = []
    for system_label, docs in by_system.items():
        crit_stats: dict[str, MeanStd] = {}
        for crit in rubric:
            vals = [d.mean_criterion_scores[crit.key] for d in docs if crit.key in d.mean_criterion_scores]
            crit_stats[crit.key] = _mean_std(vals)

        fact_stats: dict[str, MeanStd] = {}
        for name in FACT_GROUNDED_CRITERIA:
            vals = [d.mean_fact_metrics[name] for d in docs if name in d.mean_fact_metrics]
            fact_stats[name] = _mean_std(vals)

        aggregates.append(
            SystemAggregate(
                system_label=system_label,
                n_runs=len(docs),
                criterion_stats=crit_stats,
                fact_stats=fact_stats,
            )
        )
    # Stable order: our system first if present, then baseline.
    order = {SystemLabel.our_system: 0, SystemLabel.baseline_chatgpt: 1}
    aggregates.sort(key=lambda a: order.get(a.system_label, 99))
    return aggregates


__all__ = ["build_document_result", "build_system_aggregates"]
