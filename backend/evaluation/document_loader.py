"""Load external world documents for the evaluation pipeline.

The experiment still needs session notes to establish the gold reference. This
module handles the *candidate world documents* that judges score, whether they
arrive as the platform's Markdown export or its text-based PDF export.

Image-only/scanned PDFs are intentionally rejected instead of silently scoring an
empty string. Add OCR as a separate, explicit ingestion step if that use case is
needed later.
"""

from __future__ import annotations

import re
from pathlib import Path

from .schemas import GeneratorConfig, SystemLabel, WorldDocument


SUPPORTED_DOCUMENT_SUFFIXES = frozenset({".md", ".markdown", ".pdf"})


class DocumentLoadError(ValueError):
    """Raised when an evaluation candidate cannot be converted to usable text."""


def load_document_text(path: str | Path) -> str:
    """Return readable Markdown or extracted text from one candidate document.

    PDF extraction uses ``pypdf`` because the product's PDF world export is a
    text-based PDF. A PDF with no extractable text is rejected, preventing the
    evaluation from quietly judging an empty candidate.
    """
    source = Path(path).expanduser()
    if not source.is_file():
        raise DocumentLoadError(f"Candidate document does not exist or is not a file: {source}")

    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES))
        raise DocumentLoadError(f"Unsupported candidate format '{suffix or '(none)'}'. Supported formats: {supported}.")

    if suffix in {".md", ".markdown"}:
        text = source.read_text(encoding="utf-8-sig")
    else:
        try:
            from pypdf import PdfReader
        except ImportError as error:  # pragma: no cover - dependency declaration covers normal installs
            raise DocumentLoadError(
                "PDF ingestion requires pypdf. Install backend requirements before evaluating PDFs."
            ) from error
        try:
            reader = PdfReader(str(source))
            if reader.is_encrypted:
                raise DocumentLoadError(f"PDF is encrypted and cannot be evaluated: {source}")
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except DocumentLoadError:
            raise
        except Exception as error:
            raise DocumentLoadError(f"Could not read PDF candidate '{source}': {error}") from error

    # PDF generators sometimes leave invisible layout controls in extracted text.
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()
    if not text:
        detail = "The PDF may be image-only; run OCR before evaluation." if suffix == ".pdf" else "The Markdown file is empty."
        raise DocumentLoadError(f"No extractable text found in '{source}'. {detail}")
    return text


def load_world_documents(
    paths: list[str | Path],
    *,
    system_label: SystemLabel,
) -> list[WorldDocument]:
    """Create externally sourced ``WorldDocument`` instances from files.

    One file is one evaluation run. The source path and format are retained in
    the provenance fields so the resulting report is reproducible.
    """
    documents: list[WorldDocument] = []
    prefix = "baseline" if system_label == SystemLabel.baseline_chatgpt else "our_system"
    for run_index, raw_path in enumerate(paths):
        source = Path(raw_path).expanduser().resolve()
        documents.append(
            WorldDocument(
                doc_id=f"{prefix}_file{run_index + 1:02d}",
                system_label=system_label,
                run_index=run_index,
                content=load_document_text(source),
                generator=GeneratorConfig(
                    system_label=system_label,
                    provider="external_file",
                    model_name="not_provided",
                    prompt_version="external_document.v1",
                    prompt_text="External candidate document supplied for evaluation; no generation prompt is available.",
                    temperature=0.0,
                    notes=f"Source file: {source} (format: {source.suffix.lower()}).",
                ),
            )
        )
    return documents


__all__ = [
    "SUPPORTED_DOCUMENT_SUFFIXES",
    "DocumentLoadError",
    "load_document_text",
    "load_world_documents",
]
