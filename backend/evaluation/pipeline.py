"""
evaluation/pipeline.py — The orchestrator that runs the whole experiment.

This wires the pieces together in the order the methodology requires:

    1. Build the GOLD reference from the original session notes        (fact_checks)
    2. GENERATE N baseline docs + N system docs (repeated runs)        (generators)
    3. BLIND every document                                           (blinding)
    4. Each of ≥2 EVALUATORS scores every blind doc                   (judge)
         - qualitative 1–5 rubric  +  fact-grounded metrics vs gold
    5. AGGREGATE per document (across evaluators)                     (aggregate)
    6. Compute AGREEMENT + discuss disagreements                      (agreement)
    7. AGGREGATE per system (across runs) + write CONCLUSION          (aggregate/report)
    8. Assemble the ExperimentReport                                   (schemas)

Everything runs through the provider-agnostic seam, so the same call works on the
mock provider (offline demo) or on real OpenAI / Anthropic / xAI models — the only
difference is the `EvaluatorSpec.llm` / generator providers passed in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.llm_provider import LLMProvider

from .aggregate import build_document_result, build_system_aggregates
from .agreement import compute_agreement
from .blinding import blind_documents
from .fact_checks import extract_gold_facts
from .generators import (
    SessionInput,
    baseline_config,
    generate_runs,
    system_config,
)
from .judge import Judge
from .report import build_conclusion
from .rubric import DEFAULT_RUBRIC
from .schemas import (
    DocumentResult,
    EvaluatorScorecard,
    ExperimentReport,
    GoldReference,
    RubricCriterion,
    WorldDocument,
)


# =============================================================================
# Configuration objects
# =============================================================================

@dataclass
class GeneratorSpec:
    """How to produce documents for ONE system."""
    llm: LLMProvider
    provider: str
    model_name: str
    temperature: float = 0.7


@dataclass
class EvaluatorSpec:
    """One judge: an id + the model behind it. Provide >= 2 for agreement."""
    evaluator_id: str          # e.g. "gpt-4o-judge", "grok-judge", "human_A"
    llm: LLMProvider
    model_name: str | None = None


@dataclass
class ExperimentConfig:
    """Everything needed to run one experiment."""
    campaign_id: str
    sessions: list[SessionInput]
    baseline: GeneratorSpec
    system: GeneratorSpec
    evaluators: list[EvaluatorSpec]
    n_runs: int = 3                                    # repeated runs per system
    rubric: list[RubricCriterion] = field(default_factory=lambda: list(DEFAULT_RUBRIC))
    blind_seed: int = 1337
    disagreement_threshold: int = 2                    # spread that triggers a deep-dive
    # LLM used to synthesize disagreement discussions (defaults to first evaluator).
    discussion_llm: LLMProvider | None = None
    # Optionally supply a human-verified gold reference instead of extracting one.
    gold_reference: GoldReference | None = None
    gold_extraction_llm: LLMProvider | None = None     # defaults to first evaluator
    # Optional pre-generated candidate documents. When supplied, the pipeline
    # scores these files rather than calling either generator. Session notes are
    # still required for the fact-grounded gold reference.
    external_documents: list[WorldDocument] | None = None


# =============================================================================
# The run
# =============================================================================

def run_experiment(config: ExperimentConfig) -> ExperimentReport:
    if len(config.evaluators) < 2:
        # Not fatal, but the methodology asks for >= 2 so agreement is meaningful.
        print("[eval] WARNING: fewer than 2 evaluators — agreement will be undefined.")

    # --- 1. Gold reference from the notes ---------------------------------
    if config.gold_reference is not None:
        gold = config.gold_reference
        print(f"[eval] using supplied gold reference: {len(gold.facts)} facts")
    else:
        gold_llm = config.gold_extraction_llm or config.evaluators[0].llm
        print("[eval] extracting gold reference from session notes ...")
        gold = extract_gold_facts(
            gold_llm,
            campaign_id=config.campaign_id,
            sessions=config.sessions,
        )
        print(f"[eval]   -> {len(gold.facts)} gold facts "
              f"({len(gold.relationship_facts)} relationships)")

    # --- 2. Generate repeated runs for both systems -----------------------
    if config.external_documents is not None:
        if not config.external_documents:
            raise ValueError("external_documents was supplied but contains no candidate documents")
        documents = config.external_documents
        print(f"[eval] evaluating {len(documents)} externally supplied document(s) ...")
        generator_configs = list({doc.generator.model_dump_json(): doc.generator for doc in documents}.values())
        runs_per_system = min(
            sum(doc.system_label.value == "baseline_chatgpt" for doc in documents),
            sum(doc.system_label.value == "our_system" for doc in documents),
        )
    else:
        base_cfg = baseline_config(
            model_name=config.baseline.model_name,
            provider=config.baseline.provider,
            temperature=config.baseline.temperature,
        )
        sys_cfg = system_config(
            model_name=config.system.model_name,
            provider=config.system.provider,
            temperature=config.system.temperature,
        )
        print(f"[eval] generating {config.n_runs} run(s) per system ...")
        documents = (
            generate_runs(config.baseline.llm, config.sessions, config=base_cfg, n_runs=config.n_runs)
            + generate_runs(config.system.llm, config.sessions, config=sys_cfg, n_runs=config.n_runs)
        )
        generator_configs = [sys_cfg, base_cfg]
        runs_per_system = config.n_runs

    # --- 3. Blind everything ----------------------------------------------
    blinded, key = blind_documents(documents, seed=config.blind_seed)
    print(f"[eval] blinded {len(blinded)} documents: {', '.join(key.blind_ids)}")

    # --- 4. Every evaluator scores every blind document -------------------
    judges = [
        Judge(spec.llm, spec.evaluator_id, model_name=spec.model_name, rubric=config.rubric)
        for spec in config.evaluators
    ]
    scorecards_by_blind: dict[str, list[EvaluatorScorecard]] = {}
    for doc in blinded:
        cards: list[EvaluatorScorecard] = []
        for judge in judges:
            print(f"[eval]   {judge.evaluator_id} scoring {doc.blind_id} ...")
            cards.append(judge.evaluate(doc, gold))
        scorecards_by_blind[doc.blind_id] = cards

    # --- 5. Aggregate per document (across evaluators) --------------------
    document_results: list[DocumentResult] = [
        build_document_result(blind_id, cards, key, rubric=config.rubric)
        for blind_id, cards in scorecards_by_blind.items()
    ]

    # --- 6. Agreement + disagreement discussions --------------------------
    discussion_llm = config.discussion_llm or (config.evaluators[0].llm if config.evaluators else None)
    agreement = compute_agreement(
        scorecards_by_blind,
        rubric=config.rubric,
        spread_threshold=config.disagreement_threshold,
        llm=discussion_llm,
    )
    # Stamp the (now-safe-to-reveal) system identity onto each disagreement.
    for d in agreement.disagreements:
        d.system_label = key.system_of(d.blind_id)

    # --- 7. Aggregate per system + conclusion -----------------------------
    system_aggregates = build_system_aggregates(document_results, rubric=config.rubric)

    report = ExperimentReport(
        campaign_id=config.campaign_id,
        n_runs_per_system=runs_per_system,
        generator_configs=generator_configs,
        evaluator_ids=[e.evaluator_id for e in config.evaluators],
        rubric=config.rubric,
        gold_reference=gold,
        document_results=document_results,
        agreement=agreement,
        system_aggregates=system_aggregates,
        created_at=datetime.now(timezone.utc),
    )
    report.conclusion = build_conclusion(report)
    print("[eval] done.")
    return report


__all__ = [
    "GeneratorSpec",
    "EvaluatorSpec",
    "ExperimentConfig",
    "run_experiment",
]
