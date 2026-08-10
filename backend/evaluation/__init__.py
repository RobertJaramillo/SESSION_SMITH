"""
backend.evaluation — Evaluation pipeline for the AI Campaign Orchestration Platform.

Compares our system's world documents against a ChatGPT baseline using a blind,
multi-evaluator, fact-grounded methodology. See README.md in this package for the
full methodology, and AI_ARCHITECTURE.md §14 for how it fits the overall design.

Typical use:

    from backend.evaluation import run_experiment, ExperimentConfig, ...

Or run the offline demo:

    python -m backend.evaluation.run_evaluation
"""

from __future__ import annotations

from .pipeline import (
    EvaluatorSpec,
    ExperimentConfig,
    GeneratorSpec,
    run_experiment,
)
from .rubric import DEFAULT_RUBRIC
from .report import render_markdown, save_report
from .document_loader import DocumentLoadError, load_document_text, load_world_documents
from .schemas import ExperimentReport

__all__ = [
    "run_experiment",
    "ExperimentConfig",
    "GeneratorSpec",
    "EvaluatorSpec",
    "DEFAULT_RUBRIC",
    "ExperimentReport",
    "render_markdown",
    "save_report",
    "DocumentLoadError",
    "load_document_text",
    "load_world_documents",
]
