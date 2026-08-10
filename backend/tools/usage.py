"""
usage.py — Usage accounting (cost/latency).

Logs tokens, cost, latency, model, and prompt version for one call. Powers
budgets and the usage dashboard (AI_ARCHITECTURE.md §15.1).
"""

from __future__ import annotations

import uuid

from backend.llm_provider import LLMResponse
from backend.schemas import AIJob, UsageEvent
from backend.store import get_store


def record_usage_event(job: AIJob, llm: LLMResponse) -> UsageEvent:
    """Log tokens, estimated cost, latency, model, prompt version for one call
    (AI_ARCHITECTURE.md §15.1). Powers budgets and the usage dashboard."""
    event = UsageEvent(
        id=str(uuid.uuid4()),
        job_id=job.id,
        campaign_id=job.campaign_id,
        model_provider=llm.model_provider,
        model_name=llm.model_name,
        prompt_version=llm.prompt_version,
        input_tokens=llm.input_tokens,
        output_tokens=llm.output_tokens,
        estimated_cost_usd=llm.estimated_cost_usd,
        latency_ms=llm.latency_ms,
    )
    return get_store().save_usage_event(event)


__all__ = ["record_usage_event"]
