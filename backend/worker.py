"""
worker.py — AI workflows (a.k.a. "the AI-parser") = orchestration over tools.

The AI-parser is not a tool. It is a workflow that calls the tools in the
tools package in a fixed order; every workflow below reuses the same tool
set, which is why the tools live in their own module.

    extract_memory()        - notes -> pending proposals
    build_world()            - GM entries -> a world bible -> pending proposals
    generate_session_prep() - approved canon -> a prep draft

None of these workflows can create canon directly. extract_memory and
build_world only ever produce PENDING proposals; a human GM promotes them to
canon via a separate review API. This enforces "the AI may propose, but the
GM decides" at the code level.

The worker loop (claim pending ai_jobs -> dispatch -> mark done) is sketched
at the bottom as skeleton wiring for a future queue-backed worker; the real
work lives in the tools package.
"""

from __future__ import annotations

from typing import Callable

import backend.tools as tools
from backend.llm_provider import LLMProvider
from backend.schemas import (
    AIJob,
    ContextPackage,
    ExtractionOutput,
    JobType,
    MemoryProposal,
    SessionPrep,
    SessionPrepOutput,
    WorldBible,
    WorldFramework,
)


# ---------------------------------------------------------------------------
# Workflow 1: the AI-parser — extract proposals from a raw session note
# ---------------------------------------------------------------------------

def extract_memory(job: AIJob, note_id: str | None, raw_note: str, llm: LLMProvider) -> list[MemoryProposal]:
    """notes (untrusted) -> pending proposals (review queue). No canon is written."""
    # 1. Frame the world (tone/constraints)
    tools.load_campaign_context(job.campaign_id)

    # 2. Retrieve APPROVED CANON ONLY, with the raw note carried as labeled data
    context = tools.retrieve_relevant_memory(
        campaign_id=job.campaign_id,
        task=JobType.extract_memory,
        session_id=job.session_id,
        raw_note=raw_note,
    )

    # 3. Build the versioned, injection-guarded prompt
    req = tools.build_prompt(context, prompt_version="note_extraction.v1")

    # 4. Call the model (through the provider-agnostic seam)
    resp = tools.call_llm_provider(llm, req)

    # 5. Validate against the contract BEFORE storing anything
    output: ExtractionOutput = tools.validate_structured_output(resp.raw_text, ExtractionOutput)

    # 6. Store as PENDING proposals + 7. record usage
    proposals = tools.store_memory_proposals(job.campaign_id, job, output, note_id, resp)
    tools.record_usage_event(job, resp)
    return proposals


# ---------------------------------------------------------------------------
# Workflow 1b: two-pass world build — develop a world bible, then expand it into
# rich, interlinked canon. Fixes the "thin, disjointed" world: Stage 1 gives the
# whole build a shared foundation (named entities, tensions) so Stage 2's per-
# category proposals interlock. Entries + bible are embedded DIRECTLY in the
# prompts (not via the empty-at-build trusted corpus), so the model isn't blind.
# ---------------------------------------------------------------------------

def generate_world_bible(job: AIJob, world_framework: WorldFramework | None, entries_text: str, llm: LLMProvider) -> WorldBible:
    """Stage 1: develop a cohesive world bible from the GM's entries + tone."""
    context = ContextPackage(
        task=JobType.extract_memory,
        campaign_id=job.campaign_id or "",
        world_framework=world_framework,
        world_entries=entries_text or None,
    )
    req = tools.build_prompt(context, prompt_version="world_bible.v1")
    resp = tools.call_llm_provider(llm, req)
    bible: WorldBible = tools.validate_structured_output(resp.raw_text, WorldBible)
    tools.record_usage_event(job, resp)
    return bible


# Categories per expansion call. A model asked to exhaustively cover an 18-item
# checklist in one freeform completion tends to satisfy the qualitative "rich,
# specific" instructions on a handful of items and stop there, well under its
# available output budget — an instruction-following gap, not a length limit.
# A short checklist per call is something a model reliably completes in full;
# the shared world bible keeps every batch grounded in the same names and
# tensions so the result still reads as one coherent world.
_EXPAND_BATCH_SIZE = 5


# Fires after each batch (and its retry, if any) with the categories confirmed
# covered SO FAR (cumulative) and the total requested, so a caller can surface
# real build progress instead of a generic "still working" message.
ProgressCallback = Callable[[list[str], int], None]


def _run_expand_batch(job: AIJob, bible: WorldBible, entries_text: str, labels: list[str], llm: LLMProvider) -> tuple[list[MemoryProposal], set[str]]:
    """One world_expand.v1 call for a short list of categories. Returns the
    stored proposals plus the set of categories actually covered, so the
    caller can detect (and retry) whatever the model skipped."""
    focus = "Expand the world into rich, interlinked canon for each category below.\n"
    focus += "\n".join(f"[{label}]" for label in labels)
    context = ContextPackage(
        task=JobType.extract_memory,
        campaign_id=job.campaign_id or "",
        gm_instructions=focus,
        world_entries=entries_text or None,
        world_bible=bible.as_prompt_block(),
    )
    req = tools.build_prompt(context, prompt_version="world_expand.v1")
    resp = tools.call_llm_provider(llm, req)
    output: ExtractionOutput = tools.validate_structured_output(resp.raw_text, ExtractionOutput)
    stored = tools.store_memory_proposals(job.campaign_id, job, output, None, resp)
    tools.record_usage_event(job, resp)
    return stored, {p.category.value for p in stored}


# Bounds the pass loop below. A category still missing after a pass gets folded
# into the next pass's (shrinking) batches and asked for again — this caps how
# many times a stubborn category can retry so cost/time can't run away.
_MAX_EXPAND_PASSES = 4


def expand_world(
    job: AIJob,
    bible: WorldBible,
    entries_text: str,
    categories: list[str],
    llm: LLMProvider,
    on_progress: ProgressCallback | None = None,
) -> list[MemoryProposal]:
    """Stage 2: expand the bible into rich canon proposals for each category, in
    small batches so every requested category is reliably covered. Even a short
    batch, the model sometimes skips a category while staying well under its
    token budget (an instruction-following gap, not a length limit) — so any
    category still missing after a pass is folded into the next, smaller pass
    and asked for again, until every category has at least one proposal or
    _MAX_EXPAND_PASSES is reached. Multiple proposals per category (the model
    volunteering more than one) are kept — this only guarantees a floor, not
    a ceiling."""
    all_proposals: list[MemoryProposal] = []
    completed: list[str] = []
    remaining = list(categories)

    for _pass in range(_MAX_EXPAND_PASSES):
        if not remaining:
            break
        covered_this_pass: set[str] = set()
        for start in range(0, len(remaining), _EXPAND_BATCH_SIZE):
            batch = remaining[start : start + _EXPAND_BATCH_SIZE]
            stored, covered = _run_expand_batch(job, bible, entries_text, batch, llm)
            all_proposals.extend(stored)
            covered_this_pass |= covered
            completed.extend(label for label in batch if label in covered)
            if on_progress:
                on_progress(list(completed), len(categories))
        remaining = [label for label in remaining if label not in covered_this_pass]

    return all_proposals


def build_world(
    job: AIJob,
    entries_text: str,
    categories: list[str],
    llm: LLMProvider,
    on_progress: ProgressCallback | None = None,
) -> list[MemoryProposal]:
    """The one-time world build: bible (Stage 1) -> grounded expansion (Stage 2).
    Produces PENDING proposals only; sealing is a separate GM action."""
    _campaign, framework = tools.load_campaign_context(job.campaign_id)
    bible = generate_world_bible(job, framework, entries_text, llm)
    return expand_world(job, bible, entries_text, categories, llm, on_progress=on_progress)


# ---------------------------------------------------------------------------
# Workflow 2: generate session prep from approved canon
# ---------------------------------------------------------------------------

def generate_session_prep(job: AIJob, focus: str | None, llm: LLMProvider, manual_memories: str | None = None) -> SessionPrep:
    """approved canon -> editable prep draft (reuses the same tools).

    `manual_memories` is the GM's own free-text pick of what the prep should draw
    from, on top of whatever automatic retrieval finds — optional; a blank value
    behaves exactly as if it were never passed.
    """
    tools.load_campaign_context(job.campaign_id)
    context = tools.retrieve_relevant_memory(
        campaign_id=job.campaign_id,
        task=JobType.generate_session_prep,
        session_id=job.session_id,
        gm_instructions=focus,
        manual_memories=manual_memories,
    )
    req = tools.build_prompt(context, prompt_version="session_prep.v1")
    resp = tools.call_llm_provider(llm, req)
    output: SessionPrepOutput = tools.validate_structured_output(resp.raw_text, SessionPrepOutput)
    prep = tools.store_session_prep(job.campaign_id, job, output, job.session_id, resp)
    tools.record_usage_event(job, resp)
    return prep


# ---------------------------------------------------------------------------
# The worker loop — claim a pending job and dispatch to the right workflow
# ---------------------------------------------------------------------------

def run_job(job: AIJob, llm: LLMProvider, **inputs) -> None:
    """Dispatch one claimed job. In the real loop, wrap in try/except to set
    JobStatus.failed + error, and JobStatus.succeeded + result on success."""
    if job.job_type == JobType.extract_memory:
        extract_memory(job, inputs["note_id"], inputs["raw_note"], llm)
    elif job.job_type == JobType.generate_session_prep:
        generate_session_prep(job, inputs.get("focus"), llm)
    else:
        raise ValueError(f"unhandled job_type: {job.job_type}")


def poll_loop(llm: LLMProvider) -> None:
    """Prototype: SELECT one ai_job WHERE status='pending' -> mark 'running' ->
    run_job -> mark 'succeeded'/'failed'. Poll every few seconds
    (SOFTWARE_ARCHITECTURE.md §4.5). Replace with a real queue later."""
    raise NotImplementedError
