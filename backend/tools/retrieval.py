"""
retrieval.py — Retrieval (RAG) tool. APPROVED CANON ONLY.

This is the trust boundary (AI_ARCHITECTURE.md §12.2): retrieval MUST filter to
approved canon and MUST NOT surface raw notes or pending/rejected proposals.

The actual retrieval logic lives in `backend.rag` (chunking, scoring, the trust
filter, ContextPackage assembly). This tool is the thin worker-facing wrapper:
it obtains the campaign's `CampaignCorpus` from `backend.store` and delegates.
Tests and the offline demo may pass `corpus=`/`retriever=` explicitly to bypass
the store.
"""

from __future__ import annotations

from backend.rag import CampaignCorpus, Retriever, assemble_context_package
from backend.schemas import ContextPackage, JobType
from backend.store import get_store


def retrieve_relevant_memory(
    campaign_id: str,
    task: JobType,
    session_id: str | None = None,
    raw_note: str | None = None,
    gm_instructions: str | None = None,
    manual_memories: str | None = None,
    *,
    corpus: CampaignCorpus | None = None,
    retriever: Retriever | None = None,
) -> ContextPackage:
    """Assemble the ContextPackage the model will see (delegates to backend.rag).

    Filters to approved canon (world_entries tagged 'approved_canon', canon_events
    status='active', active entities) and NEVER includes raw notes, pending, or
    rejected proposals — `backend.rag.CampaignCorpus.trusted()` enforces this.
    `raw_note` is carried in its own labeled ContextPackage field for extraction —
    as DATA, not trusted context. `manual_memories` is GM-authored and trusted,
    unlike `raw_note` — specific memories the GM wants included alongside whatever
    retrieval finds automatically. Retrieval itself is embedding-free lexical/tag/
    recency scoring (AI_ARCHITECTURE.md §9.2)."""
    if corpus is None:
        corpus = get_store().get_corpus(campaign_id)
    return assemble_context_package(
        corpus,
        task,
        session_id=session_id,
        raw_note=raw_note,
        gm_instructions=gm_instructions,
        manual_memories=manual_memories,
        retriever=retriever,
    )


__all__ = ["retrieve_relevant_memory"]
