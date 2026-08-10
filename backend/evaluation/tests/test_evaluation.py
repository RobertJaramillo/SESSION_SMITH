"""
Tests for the evaluation pipeline.

These are fast, offline sanity checks (no API calls — they use the DemoProvider).
They guard the two things most likely to break silently:
  • the agreement statistics (a wrong kappa would quietly mislead the writeup), and
  • the end-to-end wiring (that a full experiment runs and the report is coherent).
"""

from __future__ import annotations

from types import SimpleNamespace

from reportlab.pdfgen import canvas

from backend.llm_provider import LLMRequest, OpenAIProvider
from backend.evaluation.agreement import quadratic_weighted_kappa, compute_agreement
from backend.evaluation.dataset import load_sessions
from backend.evaluation.document_loader import DocumentLoadError, load_document_text, load_world_documents
from backend.evaluation.fixtures import DemoProvider
from backend.evaluation.pipeline import (
    EvaluatorSpec,
    ExperimentConfig,
    GeneratorSpec,
    run_experiment,
)
from backend.evaluation.run_evaluation import _build_specs
from backend.evaluation.schemas import (
    CriterionScore,
    EvaluatorScorecard,
    SystemLabel,
)


def test_document_loader_reads_markdown_and_pdf(tmp_path):
    markdown = tmp_path / "world.md"
    markdown.write_text("# Veyr\n\nThe party reached Brackenford.", encoding="utf-8")
    assert load_document_text(markdown) == "# Veyr\n\nThe party reached Brackenford."

    pdf = tmp_path / "world.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(72, 720, "Veyr world export: the party reached Brackenford.")
    c.save()
    assert "party reached Brackenford" in load_document_text(pdf)

    documents = load_world_documents([markdown, pdf], system_label=SystemLabel.our_system)
    assert [doc.run_index for doc in documents] == [0, 1]
    assert all(doc.generator.provider == "external_file" for doc in documents)


def test_document_loader_rejects_unknown_or_empty_input(tmp_path):
    unknown = tmp_path / "world.txt"
    unknown.write_text("not accepted", encoding="utf-8")
    try:
        load_document_text(unknown)
    except DocumentLoadError as error:
        assert "Unsupported candidate format" in str(error)
    else:
        raise AssertionError("unsupported format should fail")

    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    try:
        load_document_text(empty)
    except DocumentLoadError as error:
        assert "No extractable text" in str(error)
    else:
        raise AssertionError("empty document should fail")


def test_openai_provider_uses_json_mode_only_for_schema_requests():
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="# World document"))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            )

    provider = OpenAIProvider("test-key")
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    provider.generate_structured(LLMRequest(system_prompt="system", user_prompt="user", prompt_version="eval_generation"))
    provider.generate_structured(LLMRequest(
        system_prompt="system", user_prompt="user", prompt_version="eval_judge",
        response_json_schema={"type": "object"},
    ))

    assert "response_format" not in calls[0]
    assert calls[1]["response_format"] == {"type": "json_object"}


def test_openai_evaluation_specs_reuse_the_main_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    baseline, system, evaluators = _build_specs("openai", generation_model="gpt-4o-mini")
    assert baseline.llm is system.llm
    assert baseline.provider == "openai"
    assert len(evaluators) == 2
    assert {e.model_name for e in evaluators} == {"gpt-4o", "gpt-4o-mini"}


# --- Statistics ---------------------------------------------------------------

def test_kappa_perfect_agreement():
    assert quadratic_weighted_kappa([1, 3, 5, 2], [1, 3, 5, 2]) == 1.0


def test_kappa_constant_but_equal_is_one():
    # No variance but identical -> should read as perfect agreement, not divide-by-zero.
    assert quadratic_weighted_kappa([4, 4, 4], [4, 4, 4]) == 1.0


def test_kappa_disagreement_is_low():
    # Systematic opposite ratings -> strongly negative / low.
    k = quadratic_weighted_kappa([1, 1, 1, 5], [5, 5, 5, 1])
    assert k < 0.5


def test_compute_agreement_flags_disagreement():
    # Two evaluators, one document, one criterion, 2-point gap -> flagged.
    cards = {
        "DOC_A": [
            EvaluatorScorecard(
                evaluator_id="A", blind_id="DOC_A",
                criterion_scores=[CriterionScore(criterion_key="depth_completeness", score=5, justification="x")],
            ),
            EvaluatorScorecard(
                evaluator_id="B", blind_id="DOC_A",
                criterion_scores=[CriterionScore(criterion_key="depth_completeness", score=3, justification="y")],
            ),
        ]
    }
    report = compute_agreement(cards, spread_threshold=2)
    assert len(report.disagreements) == 1
    assert report.disagreements[0].spread == 2


# --- End to end ---------------------------------------------------------------

def test_experiment_runs_end_to_end():
    campaign_id, sessions = load_sessions()
    config = ExperimentConfig(
        campaign_id=campaign_id,
        sessions=sessions[:3],              # keep the test fast
        baseline=GeneratorSpec(DemoProvider("base"), "demo", "demo-baseline"),
        system=GeneratorSpec(DemoProvider("sys"), "demo", "demo-system"),
        evaluators=[
            EvaluatorSpec("judge_A", DemoProvider("A", strictness=0)),
            EvaluatorSpec("judge_B", DemoProvider("B", strictness=1)),
        ],
        n_runs=2,
    )
    report = run_experiment(config)

    # 2 systems × 2 runs = 4 documents, each scored by 2 evaluators.
    assert len(report.document_results) == 4
    assert all(len(dr.scorecards) == 2 for dr in report.document_results)

    # The rigged demo should have our system beat the baseline on preservation.
    aggs = {a.system_label: a for a in report.system_aggregates}
    ours = aggs[SystemLabel.our_system].fact_stats["preservation_rate"].mean
    base = aggs[SystemLabel.baseline_chatgpt].fact_stats["preservation_rate"].mean
    assert ours > base

    # Report must serialize cleanly (it gets written to report.json).
    assert report.model_dump_json()
