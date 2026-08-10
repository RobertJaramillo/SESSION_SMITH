"""
evaluation/judge.py — A blind LLM-as-judge evaluator.

A `Judge` wraps one evaluator model (e.g. GPT-4o, or Grok, or Claude) and produces
a full EvaluatorScorecard for one blinded document. The methodology needs AT LEAST
TWO judges (reviewer refinement #2) so we can measure agreement — this class is
instantiated once per evaluator and each judge scores every document.

A judge produces BOTH halves of the rubric for the document it sees:
  • the qualitative 1–5 criterion scores + justifications (this file's prompt), and
  • the fact-grounded metrics (delegated to fact_checks.py with the SAME model),
so that both the subjective and the objective criteria get an inter-evaluator
agreement signal.

Blindness is enforced structurally: the judge is handed ONLY `blind_id` and
`content`. It never receives `system_label`, the generator config, or any hint of
which pipeline produced the document.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.llm_provider import LLMProvider

from .fact_checks import score_facts_against_document
from .llm_json import generate_json
from .rubric import DEFAULT_RUBRIC, render_rubric_for_prompt
from .schemas import (
    CriterionScore,
    EvaluatorScorecard,
    GoldReference,
    RubricCriterion,
    WorldDocument,
)

JUDGE_PROMPT_VERSION = "eval_judge_qualitative.v1"


class _CriterionScoreLLM(BaseModel):
    criterion_key: str
    score: int
    justification: str


class _JudgeLLM(BaseModel):
    """What we ask the judge model to return for the qualitative half."""
    criterion_scores: list[_CriterionScoreLLM] = Field(default_factory=list)
    overall_comment: str = ""


_JUDGE_SYSTEM_PROMPT = """\
You are an impartial expert evaluator of tabletop RPG "world documents" — reference
documents a Game Master would use to run a campaign. You are grading ONE document.

You do NOT know who or what produced this document. Do not speculate about it.
Judge only the text in front of you, on its own merits, using the rubric.

For EACH rubric criterion, give:
  - an integer score from 1 to 5 (use the anchor descriptions literally), and
  - a concise justification citing specifics from the document.

Be calibrated and critical: reserve 5 for genuinely excellent work and 1 for
genuinely poor work. Return ONLY JSON matching the schema.

RUBRIC:
{rubric}
"""


class Judge:
    """One evaluator. Reuse across all documents so `evaluator_id` is stable."""

    def __init__(
        self,
        llm: LLMProvider,
        evaluator_id: str,
        model_name: str | None = None,
        rubric: list[RubricCriterion] | None = None,
    ) -> None:
        self.llm = llm
        self.evaluator_id = evaluator_id
        self.model_name = model_name
        self.rubric = rubric or DEFAULT_RUBRIC

    def evaluate(self, document: WorldDocument, gold: GoldReference) -> EvaluatorScorecard:
        """Score one blinded document. Requires `document.blind_id` to be set —
        we pass ONLY the blind id and content onward, never the true identity."""
        if not document.blind_id:
            raise ValueError("Judge.evaluate requires a blinded document (blind_id is None)")

        # --- Qualitative half: the 1–5 rubric ---------------------------------
        system_prompt = _JUDGE_SYSTEM_PROMPT.format(
            rubric=render_rubric_for_prompt(self.rubric)
        )
        user_prompt = (
            f"DOCUMENT {document.blind_id} — grade this document:\n\n"
            f"{document.content}"
        )
        qual = generate_json(
            self.llm,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            prompt_version=JUDGE_PROMPT_VERSION,
            schema=_JudgeLLM,
            model_name=self.model_name,
            temperature=0.0,
        )

        # Keep only known criteria, clamp to 1–5, and don't crash on a missing one.
        valid_keys = {c.key for c in self.rubric}
        criterion_scores = [
            CriterionScore(
                criterion_key=cs.criterion_key,
                score=max(1, min(5, cs.score)),
                justification=cs.justification,
            )
            for cs in qual.criterion_scores
            if cs.criterion_key in valid_keys
        ]

        # --- Fact-grounded half: measured against the gold notes --------------
        fact_metrics = score_facts_against_document(
            self.llm,
            gold=gold,
            document_content=document.content,
            model_name=self.model_name,
        )

        return EvaluatorScorecard(
            evaluator_id=self.evaluator_id,
            blind_id=document.blind_id,
            criterion_scores=criterion_scores,
            fact_metrics=fact_metrics,
            overall_comment=qual.overall_comment or None,
        )


__all__ = ["Judge", "JUDGE_PROMPT_VERSION"]
