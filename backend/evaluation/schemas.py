"""
evaluation/schemas.py — Data contracts for the evaluation pipeline.

This is the SINGLE SOURCE OF TRUTH for the JSON shapes that flow through the
evaluation harness, mirroring how backend/schemas.py works for the product side.
Everything is Pydantic v2 so the same models validate:

    1. LLM structured outputs (judge scores, fact-check results) BEFORE we trust them.
    2. The final experiment report we persist to disk / hand to the professor.

The design implements the methodology agreed in the project's evaluation thread:

    • Baseline = ChatGPT world document, generated from the same 10 session notes
      that our own system consumes  (documented, reproducible — see GeneratorConfig).
    • Blind evaluation: judges never see which document came from which system.
    • ≥ 2 independent evaluators, with inter-evaluator agreement computed and
      disagreements discussed  (see agreement.py).
    • Two families of criteria:
        - QUALITATIVE, subjective, 1–5 rubric  (depth, consistency, coherence …)
        - FACT-GROUNDED, checkable against the original session notes
          (facts preserved / unsupported facts introduced / contradictions /
           relationship accuracy).
    • Repeated runs per system, because LLM output varies run-to-run.

See evaluation/README.md for the narrative version of this methodology, and
AI_ARCHITECTURE.md §14 for where it sits in the overall AI design.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# System identity — which pipeline produced a document
# =============================================================================

class SystemLabel(str, Enum):
    """The two things we compare. Kept as an enum so the aggregation code can
    group by system without stringly-typed bugs."""
    baseline_chatgpt = "baseline_chatgpt"   # the control: naive ChatGPT world-building
    our_system = "our_system"               # the AI Campaign Orchestration pipeline


# =============================================================================
# Reproducibility — how a document was generated (refinement #3 in the thread)
# =============================================================================

class GeneratorConfig(BaseModel):
    """Full provenance for one document generator.

    Req: clearly document ChatGPT's model, prompt, and
    generation settings, because LLM outputs vary across runs." This model is
    where that documentation lives — it is copied verbatim into the final report
    so the experiment is reproducible. It applies to BOTH the baseline and our
    system, so the comparison is apples-to-apples.
    """
    system_label: SystemLabel
    provider: str                                   # "openai" | "anthropic" | "mock" | ...
    model_name: str                                 # e.g. "gpt-4o-2024-08-06"
    prompt_version: str                             # e.g. "baseline_worldbuild.v1"
    prompt_text: str                                # the EXACT prompt template used
    temperature: float = 0.7
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    seed: Optional[int] = None                      # if the provider supports deterministic seeds
    notes: Optional[str] = None                     # anything else needed to reproduce


# =============================================================================
# The artifact under evaluation — a "world document"
# =============================================================================

class WorldDocument(BaseModel):
    """A generated world document, the unit the judges score.

    `system_label` and `generator` are STRIPPED before a judge sees the document
    (see blinding.py). During scoring the judge only ever knows `blind_id`.
    """
    doc_id: str                                     # stable id, e.g. "our_system_run02"
    system_label: SystemLabel
    run_index: int                                  # 0-based; repeated runs vary here
    content: str                                    # the document itself (markdown/plain text)
    generator: GeneratorConfig
    generated_at: Optional[datetime] = None
    blind_id: Optional[str] = None                  # assigned at blinding time, e.g. "DOC_C"


# =============================================================================
# Gold reference — "ground truth" distilled from the ORIGINAL session notes
# =============================================================================

class FactKind(str, Enum):
    fact = "fact"                                   # a standalone claim ("bridge tariffs crush commoners")
    relationship = "relationship"                   # a link between entities (character/location/event)


class GoldFact(BaseModel):
    """One important, checkable item taken from the raw session notes.

    The gold set is the yardstick for the fact-grounded criteria: it is built
    ONCE from the original notes, independent of any candidate document. For a
    rigorous run it should be human-verified (an LLM can draft it — see
    fact_checks.extract_gold_facts — but a person should confirm it).
    """
    id: str                                         # e.g. "fact_s01_003"
    text: str                                       # the fact, in one sentence
    kind: FactKind = FactKind.fact
    session_id: Optional[str] = None                # which session it came from
    entities: list[str] = Field(default_factory=list)   # named characters/locations/factions/events
    importance: str = "normal"                      # minor | normal | major | critical


class GoldReference(BaseModel):
    """The full ground-truth set for one experiment, drawn from all session notes."""
    campaign_id: str
    session_ids: list[str] = Field(default_factory=list)
    notes_text: str                                 # the concatenated raw notes (for the judge to cite)
    facts: list[GoldFact] = Field(default_factory=list)

    @property
    def relationship_facts(self) -> list[GoldFact]:
        return [f for f in self.facts if f.kind == FactKind.relationship]


# =============================================================================
# The rubric — qualitative, subjective, 1–5 criteria
# =============================================================================

class RubricCriterion(BaseModel):
    """One qualitative dimension scored 1–5. `higher_is_better=False` marks a
    reverse-scored criterion (e.g. a raw contradiction penalty), so aggregation
    and 'which system won' logic don't flip signs by accident."""
    key: str                                        # machine key, e.g. "internal_consistency"
    name: str                                       # human name, e.g. "Internal Consistency"
    description: str                                # what this dimension means
    anchors: dict[int, str] = Field(default_factory=dict)  # 1..5 -> what that score means
    higher_is_better: bool = True


# =============================================================================
# Judge outputs — what ONE evaluator produces for ONE document
# =============================================================================

class CriterionScore(BaseModel):
    """A single 1–5 rating with the evaluator's written justification.
    The justification is required: it is what makes a disagreement discussable."""
    criterion_key: str
    score: int = Field(ge=1, le=5)
    justification: str


class FactFinding(BaseModel):
    """One concrete fact-level observation, kept so the report can show examples
    (not just counts) and so a human can audit the automated fact-check."""
    gold_fact_id: Optional[str] = None              # set for preserved/contradicted gold facts
    statement: str                                  # the doc text (or gold fact) in question
    note: Optional[str] = None                      # short explanation / evidence


class FactGroundedMetrics(BaseModel):
    """The checkable-against-the-notes criteria the reviewer asked us to add.

    Counts, not opinions — every field maps to one of the reviewer's questions:
        • "How many important facts were preserved?"   -> facts_preserved / facts_total
        • "How much creative material went beyond the notes?" -> creative_additions
        • "How many factual contradictions occurred?"  -> contradictions
        • "How accurately were relationships maintained?" -> relationships_correct / total
    """
    facts_total: int = 0
    facts_preserved: int = 0
    preserved: list[FactFinding] = Field(default_factory=list)
    missing: list[FactFinding] = Field(default_factory=list)

    # Claims the document makes beyond what the notes support. Informational,
    # not scored (see rubric.FACT_METRIC_HIGHER_IS_BETTER): the platform's
    # World Builder is meant to add creative material past the notes, so this
    # isn't inherently bad — only outright contradictions (tracked separately
    # below) are.
    creative_additions: int = 0
    additions: list[FactFinding] = Field(default_factory=list)

    contradictions: int = 0                         # doc claims that contradict the notes
    contradiction_findings: list[FactFinding] = Field(default_factory=list)

    relationships_total: int = 0
    relationships_correct: int = 0
    relationship_findings: list[FactFinding] = Field(default_factory=list)

    # ---- derived rates (safe against divide-by-zero) ---------------------
    @property
    def preservation_rate(self) -> float:
        return self.facts_preserved / self.facts_total if self.facts_total else 0.0

    @property
    def relationship_accuracy(self) -> float:
        return self.relationships_correct / self.relationships_total if self.relationships_total else 0.0


class EvaluatorScorecard(BaseModel):
    """Everything one evaluator recorded for one (blind) document."""
    evaluator_id: str                               # e.g. "gpt-4o-judge" / "grok-judge" / "human_A"
    blind_id: str                                   # the anonymized doc id the evaluator saw
    criterion_scores: list[CriterionScore] = Field(default_factory=list)
    fact_metrics: FactGroundedMetrics = Field(default_factory=FactGroundedMetrics)
    overall_comment: Optional[str] = None

    def score_for(self, criterion_key: str) -> Optional[int]:
        for cs in self.criterion_scores:
            if cs.criterion_key == criterion_key:
                return cs.score
        return None


# =============================================================================
# Agreement — how much the evaluators agree, and where they don't
# =============================================================================

class CriterionAgreement(BaseModel):
    """Inter-evaluator agreement for one criterion on one document."""
    criterion_key: str
    scores_by_evaluator: dict[str, int] = Field(default_factory=dict)
    exact_agreement: bool = False                   # all evaluators gave the same score
    max_spread: int = 0                             # max - min across evaluators
    mean_abs_diff: float = 0.0                       # mean pairwise |difference|
    quadratic_weighted_kappa: Optional[float] = None  # None when < 2 evaluators or undefined


class Disagreement(BaseModel):
    """A flagged case where evaluators diverged enough to warrant discussion.
    The reviewer explicitly asked us to "dive deeper" in these cases."""
    blind_id: str
    system_label: Optional[SystemLabel] = None      # filled after unblinding, for the report
    criterion_key: str
    scores_by_evaluator: dict[str, int] = Field(default_factory=dict)
    spread: int = 0
    discussion: str = ""                            # why they differed / who to believe


class AgreementReport(BaseModel):
    """Corpus-level agreement roll-up across all documents + the flagged cases."""
    per_criterion_kappa: dict[str, Optional[float]] = Field(default_factory=dict)
    per_criterion_exact_rate: dict[str, float] = Field(default_factory=dict)
    per_criterion_adjacent_rate: dict[str, float] = Field(default_factory=dict)  # within 1 point
    disagreements: list[Disagreement] = Field(default_factory=list)
    summary: str = ""


# =============================================================================
# Aggregation — per document (across evaluators) and per system (across runs)
# =============================================================================

class DocumentResult(BaseModel):
    """One document after merging all its evaluators: consensus (mean) scores +
    the raw scorecards so nothing is hidden."""
    doc_id: str
    blind_id: str
    system_label: SystemLabel
    run_index: int
    mean_criterion_scores: dict[str, float] = Field(default_factory=dict)
    mean_fact_metrics: dict[str, float] = Field(default_factory=dict)
    scorecards: list[EvaluatorScorecard] = Field(default_factory=list)


class MeanStd(BaseModel):
    """A tiny (mean, std, n) triple used all over the aggregate report."""
    mean: float = 0.0
    std: float = 0.0
    n: int = 0


class SystemAggregate(BaseModel):
    """One system's performance across all its repeated runs."""
    system_label: SystemLabel
    n_runs: int
    criterion_stats: dict[str, MeanStd] = Field(default_factory=dict)    # qualitative 1–5
    fact_stats: dict[str, MeanStd] = Field(default_factory=dict)         # fact-grounded metrics


class ExperimentReport(BaseModel):
    """The complete result object — serialized to report.json and rendered to
    report.md. This is the deliverable."""
    campaign_id: str
    n_runs_per_system: int
    generator_configs: list[GeneratorConfig] = Field(default_factory=list)
    evaluator_ids: list[str] = Field(default_factory=list)
    rubric: list[RubricCriterion] = Field(default_factory=list)
    gold_reference: Optional[GoldReference] = None
    document_results: list[DocumentResult] = Field(default_factory=list)
    agreement: Optional[AgreementReport] = None
    system_aggregates: list[SystemAggregate] = Field(default_factory=list)
    conclusion: str = ""
    created_at: Optional[datetime] = None


__all__ = [name for name in dir() if name[0].isupper()]
