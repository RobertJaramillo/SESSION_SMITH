"""
validation.py — Structured-output validation (schema gate).

Parses+validates model JSON against a schemas.py model so nothing invalid ever
reaches the database (AI_ARCHITECTURE.md §11).
"""

from __future__ import annotations

import json
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def validate_structured_output(raw_text: str, model: Type[T]) -> T:
    """Parse+validate the model's JSON against a schemas.py model (e.g.
    ExtractionOutput, SessionPrepOutput). Raises on invalid JSON or schema
    mismatch so nothing bad is stored. Callers may retry with a repair prompt
    or fail the job (AI_ARCHITECTURE.md §11)."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model output was not valid JSON: {exc}") from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"model output did not match {model.__name__}: {exc}") from exc


__all__ = ["validate_structured_output"]
