"""
storage.py — Storage tools: proposals (pending) and prep (draft).

NEVER writes canon directly. Proposals land in the review queue with
status=pending; only a human GM decision (a separate API path) promotes a
proposal to canon (AI_ARCHITECTURE.md §12.2).
"""

from __future__ import annotations

import uuid

from backend.llm_provider import LLMResponse
from backend.schemas import (
    AIJob,
    ExtractionOutput,
    MemoryProposal,
    ProposalStatus,
    SessionPrep,
    SessionPrepOutput,
)
from backend.store import get_store


def store_memory_proposals(
    campaign_id: str,
    job: AIJob,
    proposals_output: ExtractionOutput,
    source_note_id: str | None,
    llm: LLMResponse,
) -> list[MemoryProposal]:
    """Persist extracted proposals with status=pending (into the review queue).
    Stamps AI metadata from `llm`. Does NOT create canon_events."""
    store = get_store()
    proposals = [
        MemoryProposal(
            id=str(uuid.uuid4()),
            campaign_id=campaign_id,
            session_id=job.session_id,
            source_note_id=source_note_id,
            type=p.type,
            category=p.category,
            proposed_summary=p.proposed_summary,
            proposed_payload=p.proposed_payload,
            confidence=p.confidence,
            rationale=p.rationale,
            potential_conflicts=p.potential_conflicts,
            status=ProposalStatus.pending,
            model_provider=llm.model_provider,
            model_name=llm.model_name,
            prompt_version=llm.prompt_version,
            input_token_count=llm.input_tokens,
            output_token_count=llm.output_tokens,
            estimated_cost_usd=llm.estimated_cost_usd,
            created_by_job_id=job.id,
        )
        for p in proposals_output.proposals
    ]
    for proposal in proposals:
        store.save_proposal(proposal)
    return proposals


def store_session_prep(
    campaign_id: str,
    job: AIJob,
    prep_output: SessionPrepOutput,
    session_id: str | None,
    llm: LLMResponse,
) -> SessionPrep:
    """Persist a generated prep packet as an editable draft. Stamps AI metadata."""
    prep = SessionPrep(
        id=str(uuid.uuid4()),
        campaign_id=campaign_id,
        session_id=session_id,
        title=prep_output.title,
        summary=prep_output.summary,
        sections=prep_output,
        source_memory_ids=prep_output.source_memory_ids,
        model_provider=llm.model_provider,
        model_name=llm.model_name,
        prompt_version=llm.prompt_version,
        input_token_count=llm.input_tokens,
        output_token_count=llm.output_tokens,
        estimated_cost_usd=llm.estimated_cost_usd,
        created_by_job_id=job.id,
    )
    return get_store().save_session_prep(prep)


__all__ = ["store_memory_proposals", "store_session_prep"]
