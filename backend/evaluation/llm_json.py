"""
evaluation/llm_json.py — One reliable way to get validated JSON out of a model.

Every evaluation component that talks to a model (gold-fact extraction, the judge,
the fact-checker) needs the same thing: send a prompt, get JSON back, validate it
against a Pydantic model, don't trust anything that fails. Rather than repeat that
dance, it lives here once.

It goes through the SAME provider-agnostic seam the product uses
(backend/llm_provider.py), so the evaluator can run on the mock provider offline
or on a real OpenAI/Anthropic model with no code change — only config.
"""

from __future__ import annotations

import json
import re
from typing import Type, TypeVar

from pydantic import BaseModel

from backend.llm_provider import LLMProvider, LLMRequest

T = TypeVar("T", bound=BaseModel)


def _extract_json_blob(text: str) -> str:
    """Best-effort: pull the first JSON object/array out of a model reply.

    Real models sometimes wrap JSON in prose or ```json fences even when asked not
    to. We strip fences and, failing that, grab the outermost {...} or [...] span.
    """
    text = text.strip()
    # Strip a leading/trailing markdown fence if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    # If it already looks like JSON, use as-is.
    if text[:1] in "{[":
        return text
    # Otherwise, find the first balanced-looking JSON span.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            return text[start : end + 1]
    return text


def generate_json(
    llm: LLMProvider,
    *,
    system_prompt: str,
    user_prompt: str,
    prompt_version: str,
    schema: Type[T],
    model_name: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4000,
) -> T:
    """Call the provider and return a validated instance of `schema`.

    Defaults to temperature=0.0 because evaluation should be as reproducible as
    possible (generation, by contrast, uses higher temperature — see baseline.py).

    Raises ValueError if the reply is not valid JSON or fails schema validation.
    Callers decide whether to retry with a repair prompt or fail the run — mirrors
    the product's validate_structured_output policy (AI_ARCHITECTURE.md §11).
    """
    req = LLMRequest(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        prompt_version=prompt_version,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        response_json_schema=schema.model_json_schema(),
    )
    resp = llm.generate_structured(req)
    blob = _extract_json_blob(resp.raw_text)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{prompt_version}: model did not return valid JSON: {exc}") from exc
    return schema.model_validate(data)


__all__ = ["generate_json"]
