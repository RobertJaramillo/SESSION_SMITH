"""
evaluation/fact_checks.py — The fact-grounded criteria (reviewer refinement #1).

This is a criteria that can be CHECKED AGAINST THE ORIGINAL NOTES,
not just subjective impressions:
    • How many important facts from the notes were preserved?
    • How much creative material did the document add beyond the notes?
      (informational only — not scored; see rubric.FACT_METRIC_HIGHER_IS_BETTER)
    • How many factual contradictions occurred?
    • How accurately were character/location/event relationships maintained?
There are two steps, and they are deliberately separate:

STEP 1  extract_gold_facts(notes)      -> GoldReference
        Build the yardstick ONCE from the raw session notes, independent of any
        candidate document. An LLM drafts it; a human should verify it before a
        "real" run (the gold set is the ground truth everything is scored against).

STEP 2  score_facts_against_document(gold, doc) -> FactGroundedMetrics
        For a given document, measure it against that fixed yardstick. This runs
        once PER (document, evaluator) so the fact metrics also get an
        inter-evaluator agreement signal, not just the subjective scores.

Both steps use structured JSON output through the provider seam (llm_json.py).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.llm_provider import LLMProvider

from .generators import SessionInput
from .llm_json import generate_json
from .schemas import (
    FactFinding,
    FactGroundedMetrics,
    FactKind,
    GoldFact,
    GoldReference,
)

# Prompt versions — referenced by the mock fixtures so offline demos work, and
# recorded in the report for reproducibility.
GOLD_EXTRACTION_PROMPT_VERSION = "eval_gold_extraction.v1"
FACT_CHECK_PROMPT_VERSION = "eval_fact_check.v1"


# =============================================================================
# STEP 1 — Build the gold reference from the original notes
# =============================================================================

class _GoldFactLLM(BaseModel):
    """Shape we ask the extraction model to emit per fact."""
    text: str
    kind: FactKind = FactKind.fact
    session_id: str | None = None
    entities: list[str] = Field(default_factory=list)
    importance: str = "normal"


class _GoldExtractionLLM(BaseModel):
    facts: list[_GoldFactLLM] = Field(default_factory=list)


_GOLD_SYSTEM_PROMPT = """\
You are a meticulous analyst building a GROUND-TRUTH fact list from a tabletop RPG
campaign's raw session notes. You will later use this list to grade other documents,
so it must contain only facts that are actually stated or clearly implied by the notes.

Rules:
- Extract atomic, checkable facts (one claim each). Prefer 'major'/'critical' facts.
- Separately capture RELATIONSHIPS between named entities (character-location,
  character-faction, event-consequence, etc.) with kind="relationship".
- Do NOT invent, extrapolate, or add lore that is not in the notes.
- List the named entities involved in each fact.
Return ONLY JSON matching the provided schema.
"""


def _notes_block(sessions: list[SessionInput]) -> str:
    return "\n\n".join(f"### {s.title} ({s.session_id})\n{s.raw_notes}" for s in sessions)


def _extract_chunk_facts_once(
    llm: LLMProvider,
    chunk: list[SessionInput],
    *,
    model_name: str | None,
) -> _GoldExtractionLLM:
    return generate_json(
        llm,
        system_prompt=_GOLD_SYSTEM_PROMPT,
        user_prompt=f"SESSION NOTES (the source of truth):\n\n{_notes_block(chunk)}",
        prompt_version=GOLD_EXTRACTION_PROMPT_VERSION,
        schema=_GoldExtractionLLM,
        model_name=model_name,
        temperature=0.0,
        max_tokens=16000,
    )


def _extract_chunk_facts(
    llm: LLMProvider,
    chunk: list[SessionInput],
    *,
    model_name: str | None,
    retries: int,
) -> list[_GoldFactLLM]:
    """One chunk's extraction, retried on malformed JSON, splitting as a last resort.

    A rare failure mode of JSON-mode generation is a run that gets stuck
    repeating itself and never terminates its output cleanly, hitting the
    token ceiling mid-string every time — retrying the SAME chunk reproduces
    it more often than not, since it is triggered by that chunk's content, not
    by ordinary sampling noise. If retries don't clear it, halving the chunk
    changes the prompt enough to route around whatever triggered the loop,
    and shrinks the amount of output any one call needs to produce. Recurses
    down to single-session chunks, which should essentially never hit this.
    """
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _extract_chunk_facts_once(llm, chunk, model_name=model_name).facts
        except Exception as error:  # noqa: BLE001 - retry any transient call failure (bad JSON, timeout, ...)
            last_error = error
            print(f"[eval]   gold extraction chunk retry {attempt + 1}/{retries}: {error}")
    if len(chunk) <= 1:
        assert last_error is not None
        raise last_error
    mid = len(chunk) // 2
    print(f"[eval]   splitting a {len(chunk)}-session chunk after repeated failures")
    return (
        _extract_chunk_facts(llm, chunk[:mid], model_name=model_name, retries=retries)
        + _extract_chunk_facts(llm, chunk[mid:], model_name=model_name, retries=retries)
    )


def extract_gold_facts(
    llm: LLMProvider,
    *,
    campaign_id: str,
    sessions: list[SessionInput],
    model_name: str | None = None,
    sessions_per_chunk: int = 6,
    retries_per_chunk: int = 2,
) -> GoldReference:
    """Draft the gold-standard fact set from the raw notes.

    One LLM call over an entire long campaign's notes self-truncates: given 50+
    sessions in one prompt, the model returns a handful of "important" facts
    rather than an exhaustive list, and the fact-checker later treats anything
    outside that shortlist as unsupported — punishing thorough documents for
    covering things the (incomplete) gold set never captured. Chunking into
    groups of `sessions_per_chunk` keeps each extraction call's scope small
    enough that the model can be exhaustive within it; results are concatenated.

    NOTE: for a graded/published run, a human should review the returned facts.
    The function is intentionally the same for demo (mock) and real runs — only
    the provider differs.
    """
    chunks = [
        sessions[i : i + sessions_per_chunk]
        for i in range(0, len(sessions), sessions_per_chunk)
    ] or [[]]

    all_facts: list[_GoldFactLLM] = []
    for chunk in chunks:
        all_facts.extend(_extract_chunk_facts(llm, chunk, model_name=model_name, retries=retries_per_chunk))

    facts = [
        GoldFact(
            id=f"fact_{i:04d}",
            text=f.text,
            kind=f.kind,
            session_id=f.session_id,
            entities=f.entities,
            importance=f.importance,
        )
        for i, f in enumerate(all_facts)
    ]
    return GoldReference(
        campaign_id=campaign_id,
        session_ids=[s.session_id for s in sessions],
        notes_text=_notes_block(sessions),
        facts=facts,
    )


# =============================================================================
# STEP 2 — Score one document against the gold reference
# =============================================================================

class _FactVerdictLLM(BaseModel):
    """The model's verdict on a single gold fact w.r.t. the candidate document."""
    gold_fact_id: str
    status: str                 # "preserved" | "missing" | "contradicted"
    evidence: str = ""          # quote/paraphrase from the document (or why missing)


class _UnsupportedClaimLLM(BaseModel):
    statement: str              # a claim the document makes that the notes don't support
    why: str = ""


class _RelationshipVerdictLLM(BaseModel):
    gold_fact_id: str           # a relationship-kind gold fact
    correct: bool
    evidence: str = ""


class _FactCheckLLM(BaseModel):
    fact_verdicts: list[_FactVerdictLLM] = Field(default_factory=list)
    unsupported_claims: list[_UnsupportedClaimLLM] = Field(default_factory=list)
    relationship_verdicts: list[_RelationshipVerdictLLM] = Field(default_factory=list)


_FACT_CHECK_SYSTEM_PROMPT = """\
You are grading how FAITHFUL a candidate world document is to a fixed set of
ground-truth facts taken from a campaign's session notes. Be strict and literal.

You are given:
  (A) GROUND-TRUTH FACTS — the only things known to be true. Each has an id.
  (B) GROUND-TRUTH RELATIONSHIPS — a subset marked as relationships, with ids.
  (C) The CANDIDATE DOCUMENT to grade.

Facts are listed in campaign session order, each tagged "[session N/TOTAL]".
Some properties change over the campaign (character level, location, who
holds an item, who controls a faction). A document describing a LATER state
is not a contradiction of an EARLIER-session fact about the same property —
that is the property changing over time, not an inconsistency. Only mark
"contradicted" when both facts describe the same point in the story, or when
the document places something at a time that could not follow the timeline
(e.g. claiming an earlier level than a later session already established).

Produce, as JSON matching the schema:
  1. fact_verdicts: for EVERY ground-truth fact id, one verdict:
       - "preserved"    : the document states this fact (allowing paraphrase),
         OR states a later, consistent state of the same evolving property.
       - "missing"      : the document omits it.
       - "contradicted" : the document states something that SUBSTANTIVELY
         conflicts with it for the SAME point in the timeline — a different
         outcome, a different actor, a different place, a different number.
         Do NOT mark "contradicted" for a minor spelling/naming variant of the
         same proper noun (e.g. one added/dropped letter, different
         capitalization, singular/plural) — the ground-truth facts are
         themselves machine-extracted and can contain small transcription
         slips; treat close spelling variants as the SAME entity and mark
         "preserved" instead.
     Include short evidence (a quote/paraphrase from the document, or a note).
  2. unsupported_claims: specific, checkable claims the document makes that are
     NOT supported by the ground-truth facts (i.e. likely hallucinations). Only
     list substantive claims, not stylistic phrasing.
  3. relationship_verdicts: for EVERY relationship id, whether the document
     represents that relationship correctly (true/false) with evidence.

Judge ONLY against the ground-truth facts. Do not use outside knowledge.
Return ONLY JSON.
"""


def _format_gold_for_prompt(gold: GoldReference) -> str:
    # session_ids is already in campaign play order (dataset.py sorts sessions
    # by session_number before extraction) — use its index as a session-order
    # label so the checker can tell "this fact is from later in the campaign"
    # from "this fact conflicts with one from the same point in the story."
    # Facts with no session_id (or one outside this campaign's list) sort last,
    # labeled "?/TOTAL" rather than guessed at.
    total = len(gold.session_ids)
    order = {sid: i + 1 for i, sid in enumerate(gold.session_ids)}

    def session_label(f: GoldFact) -> str:
        n = order.get(f.session_id or "")
        return f"[session {n}/{total}]" if n else f"[session ?/{total}]"

    facts_by_kind = sorted(
        (f for f in gold.facts if f.kind == FactKind.fact),
        key=lambda f: order.get(f.session_id or "", total + 1),
    )
    rels_sorted = sorted(gold.relationship_facts, key=lambda f: order.get(f.session_id or "", total + 1))

    # Headers below must stay byte-for-byte identical to the original strings
    # ("(A) GROUND-TRUTH FACTS:" / "(B) GROUND-TRUTH RELATIONSHIPS:") — the
    # DemoProvider fixture (fixtures.py's _split_ids) splits the prompt on
    # these exact substrings; changing them silently breaks the offline demo
    # (relationship facts leak into the fact-verdict count instead of being
    # excluded). The "listed in campaign session order" note lives in
    # _FACT_CHECK_SYSTEM_PROMPT instead, not here.
    lines = ["(A) GROUND-TRUTH FACTS:"]
    for f in facts_by_kind:
        ents = f", entities: {', '.join(f.entities)}" if f.entities else ""
        lines.append(f"  {session_label(f)} [{f.id}] ({f.importance}) {f.text}{ents}")
    lines.append("\n(B) GROUND-TRUTH RELATIONSHIPS:")
    for f in rels_sorted:
        ents = f", entities: {', '.join(f.entities)}" if f.entities else ""
        lines.append(f"  {session_label(f)} [{f.id}] {f.text}{ents}")
    return "\n".join(lines)


def _score_chunk_once(
    llm: LLMProvider,
    *,
    gold_chunk: GoldReference,
    document_content: str,
    model_name: str | None,
) -> _FactCheckLLM:
    user_prompt = (
        f"{_format_gold_for_prompt(gold_chunk)}\n\n"
        f"(C) CANDIDATE DOCUMENT TO GRADE:\n\n{document_content}"
    )
    return generate_json(
        llm,
        system_prompt=_FACT_CHECK_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        prompt_version=FACT_CHECK_PROMPT_VERSION,
        schema=_FactCheckLLM,
        model_name=model_name,
        temperature=0.0,
        max_tokens=16000,
    )


def score_facts_against_document(
    llm: LLMProvider,
    *,
    gold: GoldReference,
    document_content: str,
    model_name: str | None = None,
    retries: int = 2,
    facts_per_chunk: int = 60,
) -> FactGroundedMetrics:
    """Measure one document against the gold reference -> FactGroundedMetrics.

    Runs once per (document, evaluator). The counts it returns are what feed the
    reviewer's four fact-grounded questions. The model owes one verdict per gold
    fact, so a large gold reference (a thorough campaign easily has hundreds of
    facts once gold extraction is itself chunked — see extract_gold_facts) needs
    real output headroom per call; chunking the gold facts here keeps each call's
    required output bounded, the same fix applied to gold extraction and for the
    same reason (a few-hundred-fact single call reliably truncates or times out
    even at max_tokens=16000).

    `unsupported_claims` ("creative_additions" in the report — see schemas.py's
    FactGroundedMetrics) needs care under chunking: each chunk only sees a
    SLICE of the gold facts, so the model re-flags the same non-grounded
    document content in every chunk that doesn't happen to cover it —
    deduplicated by normalized statement text below, since it is the same claim
    rediscovered, not `len(chunks)` distinct ones. This count is informational
    (see rubric.FACT_METRIC_HIGHER_IS_BETTER, which deliberately omits it): the
    platform's World Builder is meant to add creative material beyond the
    notes, so "the document says things the notes don't" isn't inherently bad
    — only outright contradictions (tracked separately) are.
    """
    chunks = [
        GoldReference(campaign_id=gold.campaign_id, session_ids=gold.session_ids,
                       notes_text="", facts=gold.facts[i : i + facts_per_chunk])
        for i in range(0, len(gold.facts), facts_per_chunk)
    ] or [gold]

    preserved, missing, contradictions, rel_findings = [], [], [], []
    rel_correct = 0
    additions_by_key: dict[str, FactFinding] = {}

    for gold_chunk in chunks:
        last_error: Exception | None = None
        out = None
        for attempt in range(retries + 1):
            try:
                out = _score_chunk_once(llm, gold_chunk=gold_chunk, document_content=document_content,
                                         model_name=model_name)
                break
            except Exception as error:  # noqa: BLE001 - retry any transient call failure
                last_error = error
                print(f"[eval]   fact-check retry {attempt + 1}/{retries}: {error}")
        if out is None:
            assert last_error is not None
            raise last_error

        for v in out.fact_verdicts:
            finding = FactFinding(gold_fact_id=v.gold_fact_id, statement=v.evidence or "", note=v.status)
            if v.status == "preserved":
                preserved.append(finding)
            elif v.status == "contradicted":
                contradictions.append(finding)
            else:
                missing.append(finding)

        for c in out.unsupported_claims:
            key = c.statement.strip().lower()
            additions_by_key.setdefault(key, FactFinding(statement=c.statement, note=c.why))

        for r in out.relationship_verdicts:
            rel_findings.append(
                FactFinding(gold_fact_id=r.gold_fact_id, statement=r.evidence or "",
                            note="correct" if r.correct else "incorrect")
            )
            if r.correct:
                rel_correct += 1

    # facts_total counts only fact-kind gold items (relationships tracked separately).
    facts_total = sum(1 for f in gold.facts if f.kind == FactKind.fact)
    additions = list(additions_by_key.values())

    return FactGroundedMetrics(
        facts_total=facts_total,
        facts_preserved=len(preserved),
        preserved=preserved,
        missing=missing,
        creative_additions=len(additions),
        additions=additions,
        contradictions=len(contradictions),
        contradiction_findings=contradictions,
        relationships_total=len(gold.relationship_facts),
        relationships_correct=rel_correct,
        relationship_findings=rel_findings,
    )


__all__ = [
    "GOLD_EXTRACTION_PROMPT_VERSION",
    "FACT_CHECK_PROMPT_VERSION",
    "extract_gold_facts",
    "score_facts_against_document",
]
