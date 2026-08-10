"""
evaluation/run_evaluation.py — CLI entrypoint for the evaluation experiment.

Offline demo (no API key, no cost — uses the DemoProvider fixtures):

    python -m backend.evaluation.run_evaluation

Real OpenAI run (uses the main application's OpenAIProvider):

    OPENAI_API_KEY=... python -m backend.evaluation.run_evaluation --provider openai --runs 5 \
        --out backend/evaluation/out

Flags:
    --dataset PATH   dataset JSON with source session notes (gold-reference input)
    --baseline-document PATH  externally generated baseline candidate (.md or .pdf; repeatable)
    --system-document PATH    platform candidate (.md or .pdf; repeatable)
    --runs N         repeated generations per system (reviewer refinement #3)
    --out DIR        where report.json + report.md are written
    --provider NAME  "demo" (offline, default) or "openai"
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # Allows a minimal runtime to use an explicitly exported key.
    def load_dotenv(*_args, **_kwargs):
        return False

from backend.llm_provider import get_provider
from .dataset import DEFAULT_DATASET, load_sessions
from .document_loader import DocumentLoadError, load_world_documents
from .fixtures import DemoProvider
from .pipeline import EvaluatorSpec, ExperimentConfig, GeneratorSpec, run_experiment
from .report import save_report
from .schemas import SystemLabel


DEFAULT_GENERATION_MODEL = "gpt-4o-mini"
DEFAULT_JUDGE_MODELS = ("gpt-4o", "gpt-4o-mini")


def _build_specs(
    provider: str,
    *,
    generation_model: str = DEFAULT_GENERATION_MODEL,
    judge_models: list[str] | None = None,
):
    """Return (baseline_spec, system_spec, evaluators) for the chosen provider.

    DEMO (default) is fully offline. The ``openai`` branch reuses the product's
    provider adapter and the same ``OPENAI_API_KEY`` configuration as the app.
    By default, the two judges use the app's existing GPT-4o and GPT-4o-mini
    model roles; callers can override this with repeated ``--judge-model`` flags.
    """
    if provider == "demo":
        # Two evaluators with different strictness -> non-trivial agreement.
        return (
            GeneratorSpec(llm=DemoProvider("chatgpt-baseline"), provider="demo",
                          model_name="demo-baseline", temperature=0.7),
            GeneratorSpec(llm=DemoProvider("our-system"), provider="demo",
                          model_name="demo-system", temperature=0.5),
            [
                EvaluatorSpec("judge_lenient", DemoProvider("judge-A", strictness=0)),
                EvaluatorSpec("judge_strict", DemoProvider("judge-B", strictness=1)),
            ],
        )

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY is required when --provider openai is selected.")
        openai = get_provider("openai", api_key=api_key)
        selected_judges = judge_models or list(DEFAULT_JUDGE_MODELS)
        if len(selected_judges) < 2:
            raise SystemExit("Provide at least two --judge-model values for meaningful evaluator agreement.")
        return (
            GeneratorSpec(openai, "openai", generation_model, temperature=0.7),
            GeneratorSpec(openai, "openai", generation_model, temperature=0.5),
            [
                EvaluatorSpec(f"openai_judge_{index + 1}_{model}", openai, model)
                for index, model in enumerate(selected_judges)
            ],
        )

    raise SystemExit(
        f"Unknown provider '{provider}'. Use --provider demo or --provider openai."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the world-document evaluation experiment.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET),
                        help="JSON session-note dataset used for fact-grounded scoring")
    parser.add_argument("--baseline-document", action="append", default=[], metavar="PATH",
                        help="external baseline world document (.md or text-based .pdf); repeatable")
    parser.add_argument("--system-document", action="append", default=[], metavar="PATH",
                        help="external AI Campaign Orchestration world document (.md or text-based .pdf); repeatable")
    parser.add_argument("--runs", type=int, default=3, help="repeated runs per system")
    parser.add_argument("--out", default=str(Path(__file__).parent / "out"))
    parser.add_argument("--provider", default="demo", choices=("demo", "openai"),
                        help="'demo' (offline) or 'openai' (uses OPENAI_API_KEY)")
    parser.add_argument("--generation-model", default=DEFAULT_GENERATION_MODEL,
                        help=f"OpenAI model for generated candidate documents (default: {DEFAULT_GENERATION_MODEL})")
    parser.add_argument("--judge-model", action="append", default=[], metavar="MODEL",
                        help="OpenAI judge model; repeat for two or more evaluators")
    args = parser.parse_args()

    # Match the main app's environment behavior so a local .env can provide the
    # key, while an explicitly exported OPENAI_API_KEY still takes precedence.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    campaign_id, sessions = load_sessions(args.dataset)
    print(f"[eval] loaded {len(sessions)} sessions from campaign '{campaign_id}'")

    baseline_spec, system_spec, evaluators = _build_specs(
        args.provider,
        generation_model=args.generation_model,
        judge_models=args.judge_model or None,
    )

    if bool(args.baseline_document) != bool(args.system_document):
        parser.error("External-document mode requires at least one --baseline-document and one --system-document.")
    if args.baseline_document and len(args.baseline_document) != len(args.system_document):
        parser.error("External-document mode requires the same number of baseline and system documents for a fair repeated-run comparison.")
    try:
        external_documents = (
            load_world_documents(args.baseline_document, system_label=SystemLabel.baseline_chatgpt)
            + load_world_documents(args.system_document, system_label=SystemLabel.our_system)
            if args.baseline_document else None
        )
    except DocumentLoadError as error:
        parser.error(str(error))

    if external_documents is None:
        print(
            "[eval] WARNING: no --system-document supplied — 'our system' will be generated "
            "by generators.py's standalone stand-in prompt, NOT by calling the real product's "
            "worker.extract_memory()/build_world(). This result does not reflect actual product "
            "output. To score the real product, export a campaign's world "
            "(GET /v1/campaigns/{id}/world-export, ideally ?scope=session_notes) and pass it "
            "via --system-document."
        )

    config = ExperimentConfig(
        campaign_id=campaign_id,
        sessions=sessions,
        baseline=baseline_spec,
        system=system_spec,
        evaluators=evaluators,
        n_runs=args.runs,
        external_documents=external_documents,
    )
    report = run_experiment(config)
    json_path, md_path, html_path = save_report(report, args.out)

    print(f"\n[eval] report written:\n  {html_path}   <- open this for charts\n  {md_path}\n  {json_path}")
    print("\n" + "=" * 70)
    print(report.conclusion)


if __name__ == "__main__":
    main()
