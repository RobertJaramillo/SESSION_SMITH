"""
schemas.py — Formal data contracts for the AI Campaign Orchestration Platform.

This file is the SINGLE SOURCE OF TRUTH for the JSON shapes that move through the
system. It uses Pydantic v2 so the same definitions serve two jobs at once:

    1. LLM structured-output validation (the AI-parser's output is checked here
       BEFORE anything is written to the database).
    2. A written domain contract the team can review and agree on.

HTTP request models are deliberately separate in ``backend.models.requests``;
they preserve the frontend's camelCase API contract while this module keeps the
domain and worker contracts in snake_case.

It reconciles the two design sources, which currently disagree in places:
    - SOFTWARE_ARCHITECTURE.md / AI_ARCHITECTURE.md (normalized tables, doc examples)
    - ashes_kestrel_10_session_data_set.json (the sample dataset's actual shape)

See DATA_MODEL.md for the table-by-table explanation in game terms.

────────────────────────────────────────────────────────────────────────────────
DECISIONS TO CONFIRM  (these are the "final JSON" questions still open — resolve
before locking the contract; each is marked inline with `# DECISION:` where it bites)
────────────────────────────────────────────────────────────────────────────────
  D1. confidence type — dataset uses categorical ("high"); docs use a float (0.86).
      Current choice below: FLOAT 0.0–1.0 (better for eval thresholds), with a
      categorical alias kept for loading the sample data. Confirm which is canonical.
  D2. IDs — human-readable strings (dataset style, e.g. "economy_foundation_001")
      vs UUIDs. Current choice: STRINGS for the prototype.
  D3. Entity model — normalized tables (Character/Faction/...) vs the dataset's
      flexible "category → entries" (WorldEntry). Current choice: HYBRID (both).
  D4. Proposal payload — is `proposed_payload` free-form JSON, or strictly typed
      per proposal `type`? Current choice: free-form dict for the prototype.
  D5. Field naming — snake_case (dataset) vs camelCase (doc examples). Current
      choice: snake_case everywhere, since Python + Postgres favor it.
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Enums — lifecycle statuses (from SOFTWARE_ARCHITECTURE.md §5.3)
# =============================================================================

class CharacterKind(str, Enum):
    pc = "pc"
    npc = "npc"


class EntityStatus(str, Enum):
    active = "active"
    archived = "archived"


class ThreadStatus(str, Enum):
    open = "open"
    resolved = "resolved"
    paused = "paused"
    abandoned = "abandoned"


class SessionStatus(str, Enum):
    planned = "planned"
    completed = "completed"
    archived = "archived"


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JobType(str, Enum):
    generate_session_prep = "generate_session_prep"
    extract_memory = "extract_memory"
    summarize_and_tag = "summarize_and_tag_session_entries"  # dataset's job_type


class ProposalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    edited_approved = "edited_approved"
    rejected = "rejected"
    superseded = "superseded"


class ProposalType(str, Enum):
    canon_event = "canon_event"
    character_update = "character_update"
    faction_update = "faction_update"
    location_update = "location_update"
    story_thread_update = "story_thread_update"


class WorldCategoryLabel(str, Enum):
    """The 18 world-building categories (frontend: WORLD_CATEGORIES labels in
    worldbuilding.ts). The AI-parser assigns one of these per proposal directly,
    rather than the category being guessed from proposal text after the fact."""
    economy = "Economy"
    politics = "Politics"
    magic_systems = "Magic Systems"
    world_artifacts = "World Artifacts"
    npcs = "NPCs"
    government_organizations = "Government Organizations"
    non_government_organizations = "Non-Government Organizations"
    laws = "Laws"
    inhabitants = "Inhabitants"
    ecosystems = "Ecosystems"
    cataclysmic_events = "Cataclysmic Events"
    general_overview = "General Overview"
    races = "Races"
    jobs_and_roles = "Jobs and Roles"
    technology_systems = "Technology Systems"
    regions = "Regions"
    era = "Era"
    player_characters = "Player Characters"


class Importance(str, Enum):
    minor = "minor"
    normal = "normal"
    major = "major"
    critical = "critical"


class CanonStatus(str, Enum):
    active = "active"
    revised = "revised"
    archived = "archived"


class ConfidenceLevel(str, Enum):
    """DECISION D1: kept so the sample dataset ("high"/"medium"/"low") can be loaded.
    Canonical confidence on Proposal is a float; use map_confidence() to convert."""
    low = "low"
    medium = "medium"
    high = "high"


def map_confidence(value: float | str | ConfidenceLevel) -> float:
    """Normalize any confidence representation to a float 0.0–1.0 (DECISION D1)."""
    if isinstance(value, (int, float)):
        return float(value)
    mapping = {"low": 0.3, "medium": 0.6, "high": 0.9}
    return mapping[str(value).lower()]


# =============================================================================
# Shared mixins
# =============================================================================

class AIMetadata(BaseModel):
    """Provenance stamped on every AI-created record (SOFTWARE_ARCHITECTURE.md §5.4).
    Kept provider-agnostic — model_provider/model_name are free-form strings so the
    LLMProvider interface can swap providers without schema changes."""
    model_provider: Optional[str] = None      # "anthropic" | "openai" | "mock"
    model_name: Optional[str] = None           # e.g. "claude-opus-4-8" — free text
    prompt_version: Optional[str] = None       # e.g. "note_extraction.v1"
    input_token_count: Optional[int] = None
    output_token_count: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    schema_version: Optional[str] = None
    created_by_job_id: Optional[str] = None


# Which workflow a piece of canon came from, derived from prompt_version rather
# than stored separately — one lookup, no risk of the tag drifting from the
# prompt_version it was derived from. extract_memory() is faithful-by-design;
# build_world() is explicitly told to invent (see _WORLD_BIBLE_SYSTEM_PROMPT /
# _WORLD_EXPAND_SYSTEM_PROMPT in tools/prompting.py) — callers that need to
# score or filter canon for faithfulness to session notes must exclude
# "world_builder" entries rather than treating all canon as equally faithful.
_WORLD_BUILDER_PROMPT_VERSIONS = frozenset({"world_bible.v1", "world_expand.v1"})
_SESSION_NOTES_PROMPT_VERSIONS = frozenset({"note_extraction.v1"})

CanonOrigin = Literal["session_notes", "world_builder", "unknown"]


def classify_canon_origin(prompt_version: Optional[str]) -> CanonOrigin:
    """Classify a canon/proposal record's originating workflow from its prompt_version.

    Returns "unknown" for records with no prompt_version (e.g. canon approved
    before this classification existed) — that history can't be recovered
    retroactively, so callers should treat "unknown" as neither workflow rather
    than guessing.
    """
    if prompt_version in _SESSION_NOTES_PROMPT_VERSIONS:
        return "session_notes"
    if prompt_version in _WORLD_BUILDER_PROMPT_VERSIONS:
        return "world_builder"
    return "unknown"


# =============================================================================
# Group 1 — Campaign shell
# =============================================================================

class Campaign(BaseModel):
    id: str                                    # DECISION D2: string IDs
    name: str
    system: Optional[str] = None
    status: Optional[str] = None
    tone: list[str] = Field(default_factory=list)
    logline: Optional[str] = None
    created_at: Optional[datetime] = None


class WorldFramework(BaseModel):
    id: str
    campaign_id: str
    premise: Optional[str] = None
    tone: Optional[str] = None
    themes: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    starting_situation: Optional[str] = None
    updated_at: Optional[datetime] = None


# =============================================================================
# Group 2 — World entities
# =============================================================================

class Character(BaseModel):
    id: str
    campaign_id: str
    name: str
    kind: CharacterKind
    ancestry: Optional[str] = None
    role: Optional[str] = None
    current_goal: Optional[str] = None
    summary: Optional[str] = None
    status: EntityStatus = EntityStatus.active
    tags: list[str] = Field(default_factory=list)


class Faction(BaseModel):
    id: str
    campaign_id: str
    name: str
    summary: Optional[str] = None
    goals: list[str] = Field(default_factory=list)
    status: EntityStatus = EntityStatus.active
    tags: list[str] = Field(default_factory=list)


class Location(BaseModel):
    id: str
    campaign_id: str
    name: str
    kind: Optional[str] = None                 # city | region | landmark | dungeon
    summary: Optional[str] = None
    status: EntityStatus = EntityStatus.active
    tags: list[str] = Field(default_factory=list)


class StoryThread(BaseModel):
    id: str
    campaign_id: str
    title: str
    summary: Optional[str] = None
    status: ThreadStatus = ThreadStatus.open
    priority: Optional[str] = None             # low | medium | high
    related_entity_ids: list[str] = Field(default_factory=list)


class WorldEntry(BaseModel):
    """Flexible lore matching the dataset's "category → entries" shape."""
    id: str                                    # e.g. "economy_foundation_001"
    campaign_id: str
    category: str                              # economy | politics | laws | magic_systems | ...
    note: Optional[str] = None
    summary: Optional[str] = None
    entry_tags: list[str] = Field(default_factory=list)   # "approved_canon" = trust marker
    date_created: Optional[datetime] = None
    last_updated: Optional[datetime] = None

    @property
    def is_approved_canon(self) -> bool:
        """The trust switch: only approved-canon entries are eligible for AI retrieval."""
        return "approved_canon" in self.entry_tags


# =============================================================================
# Group 3 — Sessions & raw notes
# =============================================================================

class Session(BaseModel):
    id: str
    campaign_id: str
    session_number: Optional[int] = None
    title: Optional[str] = None
    played_at: Optional[datetime] = None
    status: Optional[SessionStatus] = None
    summary: Optional[str] = None
    related_entry_ids: list[str] = Field(default_factory=list)


class SessionNote(BaseModel):
    """RAW, UNTRUSTED input. Stored and audited, but never fed to the AI as
    authoritative context — only handed to the extraction step as DATA to analyze."""
    id: str
    session_id: str
    content: str
    source_type: str = "manual_notes"
    created_at: Optional[datetime] = None


# =============================================================================
# Group 5 (retrieval) — the CONTEXT PACKAGE
# The intermediate structure RAG assembles and hands to the prompt builder.
# (AI_ARCHITECTURE.md §9.4) — approved canon only.
# =============================================================================

class RetrievedEntity(BaseModel):
    """A slim projection of an entity used only as model context."""
    id: str
    name: str
    summary: Optional[str] = None


class ContextPackage(BaseModel):
    """What the AI-parser reads. Note the deliberate separation: raw_note is a
    clearly-labeled field kept APART from the trusted context blocks — this is the
    prompt-injection guard expressed as data structure (AI_ARCHITECTURE.md §10.3)."""
    task: JobType
    campaign_id: str
    session_id: Optional[str] = None
    world_framework: Optional[WorldFramework] = None
    characters: list[RetrievedEntity] = Field(default_factory=list)
    factions: list[RetrievedEntity] = Field(default_factory=list)
    locations: list[RetrievedEntity] = Field(default_factory=list)
    active_story_threads: list[RetrievedEntity] = Field(default_factory=list)
    recent_canon: list[RetrievedEntity] = Field(default_factory=list)
    gm_instructions: Optional[str] = None
    raw_note: Optional[str] = None             # untrusted; present only for extraction
    world_entries: Optional[str] = None        # GM's raw world-build entries (two-pass grounding)
    world_bible: Optional[str] = None          # the developed world bible (expansion grounding)
    manual_memories: Optional[str] = None      # GM-selected memories to draw the prep from (trusted)


# =============================================================================
# AI OUTPUT CONTRACT #1 — Extraction (the AI-parser's output)
# The model MUST return ExtractionOutput. Validated here before any DB write.
# =============================================================================

class MemoryProposalOut(BaseModel):
    """One suggested canon change, produced by the AI-parser. NOT yet real —
    it lands in the review queue (memory_proposals, status=pending)."""
    type: ProposalType = ProposalType.canon_event
    category: WorldCategoryLabel = WorldCategoryLabel.general_overview  # the model picks one of the 18 world categories directly
    proposed_summary: str
    proposed_payload: dict[str, Any] = Field(default_factory=dict)  # DECISION D4: free-form
    confidence: float = Field(ge=0.0, le=1.0)  # DECISION D1: float canonical
    rationale: Optional[str] = None
    potential_conflicts: list[str] = Field(default_factory=list)
    source_note_ids: list[str] = Field(default_factory=list)

    # A live LLM (json_object mode, not strict schema) routinely drifts on these
    # enums — e.g. it puts a category slug like "magic_system" in `type`. One bad
    # value must not fail the whole batch: coerce unknowns to a safe default (the
    # GM reviews every proposal anyway) instead of raising a validation error.
    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, value: Any) -> Any:
        try:
            return ProposalType(value)
        except (ValueError, TypeError):
            return ProposalType.canon_event

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, value: Any) -> Any:
        try:
            return WorldCategoryLabel(value)
        except (ValueError, TypeError):
            return WorldCategoryLabel.general_overview

    # Same drift, different shape: a live model asked for "a short, specific
    # description" sometimes writes potential_conflicts as one string instead
    # of a single-item list. Observed live (real OpenAI run, 2026-08-09) after
    # broadening _CONFLICT_GUIDANCE to also cover note-grounding, which raised
    # how often the model populates this field at all. Wrap rather than reject.
    @field_validator("potential_conflicts", mode="before")
    @classmethod
    def _coerce_potential_conflicts(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        return value


class ExtractionOutput(BaseModel):
    """Top-level structured output for job_type=extract_memory."""
    proposals: list[MemoryProposalOut] = Field(default_factory=list)


class WorldBibleEntity(BaseModel):
    """A named anchor the whole world can reference (keeps categories cohesive)."""
    name: str
    kind: str = ""          # person | place | faction | force | ...
    note: str = ""


class WorldBible(BaseModel):
    """Structured output for prompt_version=world_bible.v1 (two-pass Stage 1).

    A bold co-author's foundation: developed from whatever the GM provided (even
    just a name + tone), it gives Stage 2 a shared premise, named entities, and
    tensions so the expanded categories interlock instead of reading as disjointed
    statements. It is a working draft, not canon.
    """
    premise: str
    tone: str = ""
    key_entities: list[WorldBibleEntity] = Field(default_factory=list)
    central_tensions: list[str] = Field(default_factory=list)
    defining_event: str = ""
    open_questions: list[str] = Field(default_factory=list)

    def as_prompt_block(self) -> str:
        """Render the bible as labeled text for the Stage-2 expansion prompt."""
        lines = [f"PREMISE: {self.premise}"]
        if self.tone:
            lines.append(f"TONE: {self.tone}")
        if self.defining_event:
            lines.append(f"DEFINING_EVENT: {self.defining_event}")
        if self.key_entities:
            lines.append("KEY_ENTITIES:")
            lines.extend(f"- {e.name} ({e.kind}): {e.note}".rstrip() for e in self.key_entities)
        if self.central_tensions:
            lines.append("CENTRAL_TENSIONS:")
            lines.extend(f"- {t}" for t in self.central_tensions)
        if self.open_questions:
            lines.append("OPEN_QUESTIONS:")
            lines.extend(f"- {q}" for q in self.open_questions)
        return "\n".join(lines)


# =============================================================================
# AI OUTPUT CONTRACT #2 — Session prep (the other workflow's output)
# (AI_ARCHITECTURE.md §7.4)
# =============================================================================

class MainBeat(BaseModel):
    title: str
    description: str
    related_memory_ids: list[str] = Field(default_factory=list)


class SessionPrepOutput(BaseModel):
    title: str
    summary: str
    opening_scene: Optional[str] = None
    main_beats: list[MainBeat] = Field(default_factory=list)
    npcs: list[str] = Field(default_factory=list)
    faction_moves: list[str] = Field(default_factory=list)
    encounters: list[str] = Field(default_factory=list)
    clues: list[str] = Field(default_factory=list)
    open_questions_for_gm: list[str] = Field(default_factory=list)
    source_memory_ids: list[str] = Field(default_factory=list)


# =============================================================================
# Group 4 — Stored AI records (proposals in review, promoted canon, prep drafts)
# =============================================================================

class MemoryProposal(AIMetadata):
    """The stored review-queue row (matches dataset's review_queue_examples)."""
    id: str
    campaign_id: str
    session_id: Optional[str] = None
    source_note_id: Optional[str] = None
    type: Optional[ProposalType] = None
    category: WorldCategoryLabel = WorldCategoryLabel.general_overview
    proposed_summary: str
    proposed_payload: dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = None
    rationale: Optional[str] = None
    potential_conflicts: list[str] = Field(default_factory=list)
    status: ProposalStatus = ProposalStatus.pending
    reviewed_at: Optional[datetime] = None
    review_reason: Optional[str] = None


class CanonEvent(AIMetadata):
    """Approved historical fact. Safe, trusted, retrievable."""
    id: str
    campaign_id: str
    summary: str
    category: Optional[str] = None  # one of the 18 world-category labels, e.g. "Economy"
    importance: Optional[Importance] = None
    related_entity_ids: list[str] = Field(default_factory=list)
    source_note_ids: list[str] = Field(default_factory=list)     # audit link to raw notes
    source_proposal_id: Optional[str] = None                     # which proposal promoted this
    status: CanonStatus = CanonStatus.active
    created_at: Optional[datetime] = None


class SessionPrep(AIMetadata):
    """AI-drafted prep the GM edits (stores a SessionPrepOutput in `sections`).

    NOT canon — a plan for a session that hasn't been played yet. Canon only
    ever comes from approved session notes or approved world-building. `status`
    tracks the GM's own approval of this prep as "the plan for next session";
    `approved_outline` is the GM's final (possibly edited) text at approval time.
    """
    id: str
    campaign_id: str
    session_id: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    sections: SessionPrepOutput
    source_memory_ids: list[str] = Field(default_factory=list)
    status: str = "draft"                            # draft | approved
    approved_outline: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# =============================================================================
# Groups 5 & 6 — Retrieval index + plumbing
# =============================================================================

class RagChunk(BaseModel):
    id: str                                    # e.g. "rag_chunk_0001"
    campaign_id: str
    category: Optional[str] = None
    entry_id: Optional[str] = None             # source row (world_entries / canon_events)
    chunk_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[list[float]] = None    # placeholder now; pgvector later


class AIJob(BaseModel):
    id: str
    campaign_id: Optional[str] = None
    session_id: Optional[str] = None
    job_type: JobType
    status: JobStatus = JobStatus.pending
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class UsageEvent(BaseModel):
    id: str
    job_id: Optional[str] = None
    campaign_id: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    latency_ms: Optional[int] = None
    created_at: Optional[datetime] = None


__all__ = [name for name in dir() if name[0].isupper()]
