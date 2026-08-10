"""
evaluation/rubric.py — The scoring rubric, in one place.

Two kinds of criteria, exactly as agreed in the evaluation thread:

  1. QUALITATIVE (this file's DEFAULT_RUBRIC): subjective dimensions a judge
     scores 1–5 with a written justification. These are the "depth / consistency
     / coherence" style criteria from the original proposal.

  2. FACT-GROUNDED (documented here, computed in fact_checks.py): objective counts
     checked against the original session notes. The reviewer asked us to ADD
     these on top of the qualitative ones, so a document can't score well just by
     "reading nicely" while quietly inventing or dropping facts.

Keeping the rubric as data (not hard-coded strings scattered through prompts)
means: the judge prompt, the report, and the aggregation all read from the SAME
definition, and a prompt-version bump is a one-line change here.
"""

from __future__ import annotations

from .schemas import RubricCriterion


# =============================================================================
# 1. Qualitative rubric — scored 1–5 by each evaluator
# =============================================================================
#
# Anchors are deliberately concrete so two different judges (or a judge and a
# human) interpret "3" the same way. This is what makes inter-evaluator
# agreement meaningful rather than noise.

DEFAULT_RUBRIC: list[RubricCriterion] = [
    RubricCriterion(
        key="depth_completeness",
        name="Depth & Completeness",
        description=(
            "How thoroughly the world document covers the material implied by the "
            "sessions: entities, factions, locations, events, and their context. "
            "Breadth AND useful detail, not padding."
        ),
        anchors={
            1: "Sparse; most of what happened is missing or reduced to a sentence.",
            2: "Covers the obvious beats only; little supporting detail.",
            3: "Covers most sessions with moderate detail; some gaps.",
            4: "Broad and detailed; only minor omissions.",
            5: "Comprehensive and richly detailed; a GM could run from it directly.",
        },
    ),
    RubricCriterion(
        key="internal_consistency",
        name="Internal Consistency",
        description=(
            "Whether the document agrees with ITSELF: names, timelines, statuses, "
            "and relationships stay stable from one section to the next."
        ),
        anchors={
            1: "Frequently contradicts itself; unusable as a reference.",
            2: "Several internal contradictions a reader would notice.",
            3: "Mostly consistent; a few reconcilable slips.",
            4: "Consistent throughout; at most one trivial slip.",
            5: "Fully self-consistent; no detectable internal contradictions.",
        },
    ),
    RubricCriterion(
        key="logical_coherence",
        name="Logical Coherence",
        description=(
            "Whether events, causes, and consequences follow sensibly — the story "
            "and world hang together and read as a coherent whole."
        ),
        anchors={
            1: "Disjointed; sections don't connect or cause/effect is broken.",
            2: "Weak connective tissue; reader must guess how things relate.",
            3: "Generally coherent with some non-sequiturs.",
            4: "Coherent and well-ordered; transitions make sense.",
            5: "Tightly reasoned; causes, consequences, and structure all cohere.",
        },
    ),
    RubricCriterion(
        key="faithfulness_to_notes",
        name="Faithfulness to Source Notes",
        description=(
            "Overall subjective sense of how faithfully the document reflects the "
            "original session notes (the numeric fact counts in FactGroundedMetrics "
            "are the objective companion to this judgment)."
        ),
        anchors={
            1: "Largely detached from the notes; much is invented.",
            2: "Loosely based on the notes; notable drift.",
            3: "Broadly faithful with some liberties.",
            4: "Faithful; only minor embellishments clearly grounded in the notes.",
            5: "Strictly faithful; every major claim is traceable to the notes.",
        },
    ),
]


# Convenience lookups -----------------------------------------------------------

RUBRIC_BY_KEY: dict[str, RubricCriterion] = {c.key: c for c in DEFAULT_RUBRIC}


# =============================================================================
# 2. Fact-grounded criteria — documented here, computed in fact_checks.py
# =============================================================================
#
# These are NOT 1–5 opinions; they are counts/rates measured against the notes.
# Listed here (rather than only in code) so the rubric lives in one place and the
# report can print definitions next to the numbers.

FACT_GROUNDED_CRITERIA: dict[str, str] = {
    "preservation_rate":
        "Fraction of important gold facts (from the notes) preserved in the document. "
        "Higher is better. Answers: 'How many important facts were preserved?'",
    "creative_additions":
        "Count of claims in the document not traceable to the notes — new material "
        "the document adds. Informational only, not scored: the platform's World "
        "Builder is meant to add creative material beyond the notes, so this isn't "
        "inherently bad on its own — outright contradictions (below) are the real "
        "signal of unfaithfulness. Answers: 'How much creative material did the "
        "document add beyond the notes?'",
    "contradictions":
        "Count of document claims that directly contradict the notes. "
        "Lower is better. Answers: 'How many factual contradictions occurred?'",
    "relationship_accuracy":
        "Fraction of character/location/faction/event relationships from the notes "
        "represented correctly. Higher is better. Answers: 'How accurately were "
        "relationships maintained?'",
}

# Direction of each fact-grounded metric, for aggregation and 'who won' logic.
# True  -> higher is better (rates)
# False -> lower is better (error counts)
# creative_additions is deliberately ABSENT: it is informational only (see its
# description above) and must never be used to declare a winner.
FACT_METRIC_HIGHER_IS_BETTER: dict[str, bool] = {
    "preservation_rate": True,
    "relationship_accuracy": True,
    "contradictions": False,
}


# =============================================================================
# Rendering — turn the rubric into prompt text for the judge
# =============================================================================

def render_rubric_for_prompt(rubric: list[RubricCriterion] | None = None) -> str:
    """Render the qualitative rubric as instruction text a judge model can follow.
    Used by judge.py so the prompt and the schema never drift apart."""
    rubric = rubric or DEFAULT_RUBRIC
    lines: list[str] = []
    for c in rubric:
        lines.append(f"- {c.name} (key: `{c.key}`) — {c.description}")
        for score in sorted(c.anchors):
            lines.append(f"    {score} = {c.anchors[score]}")
    return "\n".join(lines)


def render_fact_criteria_for_prompt() -> str:
    """Render the fact-grounded criteria definitions for the fact-check prompt."""
    return "\n".join(f"- {k}: {v}" for k, v in FACT_GROUNDED_CRITERIA.items())


__all__ = [
    "DEFAULT_RUBRIC",
    "RUBRIC_BY_KEY",
    "FACT_GROUNDED_CRITERIA",
    "FACT_METRIC_HIGHER_IS_BETTER",
    "render_rubric_for_prompt",
    "render_fact_criteria_for_prompt",
]
