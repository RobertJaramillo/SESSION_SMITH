"""
evaluation/agreement.py — Do the evaluators agree? Where don't they?

Req: "use at least two evaluators and calculate agreement between evaluators. In cases where their scores differ, write an explanation /
discussion (dive deeper in these cases)."

This module does both:

1. STATISTICS (pure Python, no numpy) on the 1–5 qualitative scores:
    - exact agreement rate            (fraction of items all judges scored equally)
    - adjacent agreement rate         (fraction within 1 point)
    - mean absolute difference        (average pairwise gap)
    - quadratic weighted Cohen's κ    (ordinal-aware; the headline agreement number)
    For > 2 evaluators we average over all evaluator pairs.

2. DISAGREEMENT DISCUSSION: any (document, criterion) where the judges' scores
    spread by >= `spread_threshold` points is flagged and written up. By default
    the write-up is assembled from the judges' own justifications; pass an
    `llm` to have a model synthesize a deeper discussion of who is more persuasive.

Why quadratic weighted kappa: plain %-agreement rewards luck and ignores that a
2-vs-3 disagreement is milder than a 1-vs-5. Quadratic weights penalize larger
gaps more, and kappa corrects for agreement expected by chance — the standard
choice for ordinal rubric scores.
"""

from __future__ import annotations

from itertools import combinations

from backend.llm_provider import LLMProvider

from .llm_json import generate_json
from .rubric import DEFAULT_RUBRIC, RUBRIC_BY_KEY
from .schemas import (
    AgreementReport,
    Disagreement,
    EvaluatorScorecard,
    RubricCriterion,
)
from pydantic import BaseModel


# =============================================================================
# Pure statistics
# =============================================================================

def quadratic_weighted_kappa(
    ratings_a: list[int],
    ratings_b: list[int],
    min_rating: int = 1,
    max_rating: int = 5,
) -> float:
    """Cohen's quadratic weighted kappa between two raters over paired ratings.

    Returns 1.0 for perfect agreement, 0.0 for chance-level, negative for
    systematic disagreement. Edge cases:
    - fewer than 1 pair            -> 0.0
    - one rater gave no variation  -> falls back to exact-match ratio in [0,1]
    """
    if not ratings_a or len(ratings_a) != len(ratings_b):
        return 0.0

    n_ratings = max_rating - min_rating + 1
    n_items = len(ratings_a)

    # Observed co-occurrence matrix O[i][j].
    observed = [[0] * n_ratings for _ in range(n_ratings)]
    for a, b in zip(ratings_a, ratings_b):
        observed[a - min_rating][b - min_rating] += 1

    # Marginal histograms.
    hist_a = [0] * n_ratings
    hist_b = [0] * n_ratings
    for a, b in zip(ratings_a, ratings_b):
        hist_a[a - min_rating] += 1
        hist_b[b - min_rating] += 1

    # Quadratic weight matrix and expected matrix.
    denom_sq = (n_ratings - 1) ** 2 or 1
    num = 0.0
    den = 0.0
    for i in range(n_ratings):
        for j in range(n_ratings):
            weight = ((i - j) ** 2) / denom_sq
            expected = hist_a[i] * hist_b[j] / n_items
            num += weight * observed[i][j]
            den += weight * expected

    if den == 0:
        # No expected disagreement (e.g. all ratings identical value) -> defer to
        # exact-match ratio so a constant-but-agreeing pair reads as 1.0.
        exact = sum(1 for a, b in zip(ratings_a, ratings_b) if a == b) / n_items
        return exact
    return 1.0 - num / den


def _pairwise_mean_kappa(score_lists: list[list[int]]) -> float | None:
    """Average quadratic weighted kappa over all evaluator pairs. None if < 2."""
    if len(score_lists) < 2:
        return None
    kappas = [
        quadratic_weighted_kappa(a, b)
        for a, b in combinations(score_lists, 2)
    ]
    return sum(kappas) / len(kappas) if kappas else None


# =============================================================================
# Disagreement write-ups
# =============================================================================

class _DiscussionLLM(BaseModel):
    discussion: str


_DISCUSSION_SYSTEM_PROMPT = """\
Two or more expert evaluators scored the SAME document on ONE rubric criterion and
disagreed. You are given the criterion, each evaluator's score, and each one's
justification. Write a short (3–5 sentence) discussion that:
- identifies the likely SOURCE of the disagreement (different reading of the
document? different strictness? one judge missed something?),
- says which position is better supported by the cited justifications, and
- notes what a human adjudicator should check to resolve it.
Be specific and even-handed. Return ONLY JSON: {"discussion": "..."}.
"""


def _template_discussion(
    criterion: RubricCriterion,
    scorecards: list[EvaluatorScorecard],
) -> str:
    """Deterministic, no-LLM discussion assembled from the judges' own words.
    Used when no `llm` is provided to compute_agreement()."""
    parts = [
        f'Evaluators disagreed on "{criterion.name}". Their scores and reasons:'
    ]
    for sc in scorecards:
        s = sc.score_for(criterion.key)
        just = next(
            (cs.justification for cs in sc.criterion_scores if cs.criterion_key == criterion.key),
            "(no justification)",
        )
        parts.append(f"  • {sc.evaluator_id} gave {s}: {just}")
    parts.append(
        "Resolution note: a human adjudicator should re-read the relevant "
        "passages and decide whether the gap reflects a real quality difference "
        "or differing strictness between evaluators."
    )
    return "\n".join(parts)


def _llm_discussion(
    llm: LLMProvider,
    criterion: RubricCriterion,
    scorecards: list[EvaluatorScorecard],
) -> str:
    """Deeper, model-synthesized discussion of a disagreement."""
    lines = [f"CRITERION: {criterion.name} — {criterion.description}", "", "EVALUATORS:"]
    for sc in scorecards:
        s = sc.score_for(criterion.key)
        just = next(
            (cs.justification for cs in sc.criterion_scores if cs.criterion_key == criterion.key),
            "",
        )
        lines.append(f"- {sc.evaluator_id}: score={s}. Justification: {just}")
    try:
        out = generate_json(
            llm,
            system_prompt=_DISCUSSION_SYSTEM_PROMPT,
            user_prompt="\n".join(lines),
            prompt_version="eval_disagreement_discussion.v1",
            schema=_DiscussionLLM,
            temperature=0.2,
        )
        return out.discussion
    except Exception:
        # Never let discussion generation fail the whole experiment.
        return _template_discussion(criterion, scorecards)


# =============================================================================
# Top-level: agreement across the whole corpus
# =============================================================================

def compute_agreement(
    scorecards_by_blind_id: dict[str, list[EvaluatorScorecard]],
    *,
    rubric: list[RubricCriterion] | None = None,
    spread_threshold: int = 2,
    llm: LLMProvider | None = None,
) -> AgreementReport:
    """Compute corpus-level agreement + flag/discuss disagreements.

    Args:
        scorecards_by_blind_id: blind_id -> the scorecards from every evaluator
                                for that document.
        spread_threshold:       min (max-min) score gap on a criterion to flag it
                                as a disagreement worth discussing. Default 2, i.e.
                                a two-point gap on a 1–5 scale.
        llm:                    if provided, disagreement discussions are model-
                                synthesized; otherwise a deterministic template is
                                assembled from the judges' justifications.
    """
    rubric = rubric or DEFAULT_RUBRIC

    # Gather, per criterion, one aligned score list per evaluator across all docs.
    # We align by iterating documents in a stable order and, within each, by a
    # stable evaluator order — so index i refers to the same document for all raters.
    per_criterion_scores: dict[str, list[list[int]]] = {c.key: [] for c in rubric}
    exact_hits: dict[str, int] = {c.key: 0 for c in rubric}
    adjacent_hits: dict[str, int] = {c.key: 0 for c in rubric}
    counted: dict[str, int] = {c.key: 0 for c in rubric}

    disagreements: list[Disagreement] = []

    for blind_id in sorted(scorecards_by_blind_id):
        cards = scorecards_by_blind_id[blind_id]
        # Stable evaluator order for alignment.
        cards = sorted(cards, key=lambda c: c.evaluator_id)
        if len(per_criterion_scores[rubric[0].key]) == 0:
            # Initialize one list slot per evaluator.
            for c in rubric:
                per_criterion_scores[c.key] = [[] for _ in cards]

        for crit in rubric:
            scores = [sc.score_for(crit.key) for sc in cards]
            if any(s is None for s in scores):
                continue
            scores = [int(s) for s in scores]
            for slot, s in enumerate(scores):
                per_criterion_scores[crit.key][slot].append(s)

            counted[crit.key] += 1
            spread = max(scores) - min(scores)
            if spread == 0:
                exact_hits[crit.key] += 1
            if spread <= 1:
                adjacent_hits[crit.key] += 1

            # Flag + discuss real disagreements.
            if spread >= spread_threshold:
                scores_by_eval = {sc.evaluator_id: sc.score_for(crit.key) for sc in cards}
                discussion = (
                    _llm_discussion(llm, crit, cards) if llm is not None
                    else _template_discussion(crit, cards)
                )
                disagreements.append(
                    Disagreement(
                        blind_id=blind_id,
                        criterion_key=crit.key,
                        scores_by_evaluator={k: int(v) for k, v in scores_by_eval.items()},
                        spread=spread,
                        discussion=discussion,
                    )
                )

    per_criterion_kappa: dict[str, float | None] = {}
    exact_rate: dict[str, float] = {}
    adjacent_rate: dict[str, float] = {}
    for crit in rubric:
        per_criterion_kappa[crit.key] = _pairwise_mean_kappa(per_criterion_scores[crit.key])
        n = counted[crit.key] or 1
        exact_rate[crit.key] = exact_hits[crit.key] / n
        adjacent_rate[crit.key] = adjacent_hits[crit.key] / n

    summary = _summarize(per_criterion_kappa, exact_rate, len(disagreements))

    return AgreementReport(
        per_criterion_kappa=per_criterion_kappa,
        per_criterion_exact_rate=exact_rate,
        per_criterion_adjacent_rate=adjacent_rate,
        disagreements=disagreements,
        summary=summary,
    )


def _summarize(
    kappa: dict[str, float | None],
    exact: dict[str, float],
    n_disagreements: int,
) -> str:
    valid = [k for k in kappa.values() if k is not None]
    mean_kappa = sum(valid) / len(valid) if valid else None
    if mean_kappa is None:
        return "Only one evaluator present — inter-evaluator agreement not defined."

    def band(k: float) -> str:
        if k < 0.0:
            return "worse than chance"
        if k < 0.20:
            return "slight"
        if k < 0.40:
            return "fair"
        if k < 0.60:
            return "moderate"
        if k < 0.80:
            return "substantial"
        return "almost perfect"

    return (
        f"Mean quadratic-weighted kappa across criteria = {mean_kappa:.2f} "
        f"({band(mean_kappa)} agreement). "
        f"{n_disagreements} (document, criterion) case(s) exceeded the disagreement "
        f"threshold and are discussed individually."
    )


__all__ = [
    "quadratic_weighted_kappa",
    "compute_agreement",
]
