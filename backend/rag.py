"""
rag.py — The Retrieval-Augmented Generation engine.

This is the ONE place the campaign's long-term memory is turned into a focused
context package for the model. Workflows (worker.py) and the `retrieve_relevant_memory`
tool depend on the functions here; they never re-implement retrieval or the trust
filter themselves. Mirrors the provider-agnostic seam of `llm_provider.py`:
a `Retriever` Protocol + concrete backends + a `get_retriever` factory, so the
MVP lexical backend can be swapped for pgvector later with zero call-site changes
(AI_ARCHITECTURE.md §9.3).

THE TRUST BOUNDARY (AI_ARCHITECTURE.md §12.2, §13) — enforced in ONE place here:
    Retrieval sees APPROVED CANON ONLY. Raw notes, pending proposals, and rejected
    proposals are never retrievable. A `raw_note` is carried through untouched and
    handed back in its own labeled `ContextPackage.raw_note` field — as DATA to
    analyze, never merged into the trusted context blocks (the prompt-injection
    guard expressed as data structure).

MVP retrieval is intentionally embedding-free (AI_ARCHITECTURE.md §9.2): lexical
term overlap + recency + importance + tag/status signals. That is enough to
demonstrate RAG without standing up a vector store. `EmbeddingRetriever` below is
the seam for the later semantic/hybrid upgrade (§9.3).

Design constraints matched to the rest of the backend:
    • Pure stdlib + pydantic — no numpy, no vector DB (DemoProvider parity: runs
      offline with no infra).
    • All I/O types come from schemas.py, so this module composes with the tools
      and the worker without new contracts.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Optional, Protocol

from pydantic import BaseModel, Field

from backend.schemas import (
    Campaign,
    CanonEvent,
    CanonStatus,
    Character,
    CharacterKind,
    ContextPackage,
    EntityStatus,
    Faction,
    Importance,
    JobType,
    Location,
    RagChunk,
    RetrievedEntity,
    Session,
    StoryThread,
    ThreadStatus,
    WorldEntry,
    WorldFramework,
)

# The tag that marks a world entry as trusted (schemas.WorldEntry.is_approved_canon).
APPROVED_CANON_TAG = "approved_canon"

# Default retrieval budget per context block. DEFAULT_CANON_LIMIT is sized to
# comfortably include an entire freshly-built world's canon (18 categories, ~1-2
# entries each) rather than lexically ranking it down — with keyword-only
# retrieval (no embeddings; see EmbeddingRetriever), ranking a small corpus down
# to a handful of "best" matches is more likely to drop something relevant than
# to help. Revisit this once campaigns' canon regularly exceeds ~40 entries —
# see KNOWN_LIMITATIONS.md.
DEFAULT_ENTITY_LIMIT = 6
DEFAULT_CANON_LIMIT = 40

# Relevance-score weights (KeywordRetriever). Lexical overlap dominates; recency and
# importance/status break ties and surface fresh, load-bearing canon.
_W_LEXICAL = 1.0
_W_RECENCY = 0.35
_W_IMPORTANCE = 0.25

_IMPORTANCE_BOOST = {
    Importance.critical: 1.0,
    Importance.major: 0.66,
    Importance.normal: 0.33,
    Importance.minor: 0.0,
}

# Small, deliberately-short stopword list so short GM instructions still retrieve.
_STOPWORDS = frozenset(
    """
    a an and are as at be but by for if in into is it its of on or that the their them
    they this to was were will with without your you our we he she his her from over under
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9']+")


# =============================================================================
# Tokenisation + lexical scoring (the embedding-free MVP core, §9.2)
# =============================================================================

def tokenize(text: Optional[str]) -> list[str]:
    """Lowercase word tokens, stopwords and 1-char noise dropped. Deterministic."""
    if not text:
        return []
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS]


def _lexical_score(query_tokens: list[str], doc_tokens: list[str]) -> float:
    """TF-weighted overlap normalised by document length.

    Rewards documents that contain many of the query's distinct terms, with a
    diminishing bonus for repeats (log tf), and divides by sqrt(len) so long
    entries don't dominate purely by size. Range is unbounded-but-small; only
    relative order matters.
    """
    if not query_tokens or not doc_tokens:
        return 0.0
    tf: dict[str, int] = {}
    for t in doc_tokens:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    for q in set(query_tokens):
        n = tf.get(q, 0)
        if n:
            score += 1.0 + math.log(n)
    return score / math.sqrt(len(doc_tokens))


def _epoch(dt) -> Optional[float]:
    """Best-effort timestamp -> float seconds; None if unknown (sorts oldest)."""
    if dt is None:
        return None
    try:
        return dt.timestamp()
    except (AttributeError, ValueError, OverflowError):
        return None


# =============================================================================
# CampaignCorpus — the loaded source material retrieval draws from
# =============================================================================

class CampaignCorpus(BaseModel):
    """Everything retrieval MAY consider for one campaign, as loaded objects.

    Populated by the storage layer (or `from_dataset` for offline demos/tests).
    Holding it as one value keeps the trust filter in a single, testable place:
    `trusted()` is the only view retrieval is ever allowed to read from.
    """

    campaign: Optional[Campaign] = None
    world_framework: Optional[WorldFramework] = None
    world_entries: list[WorldEntry] = Field(default_factory=list)
    characters: list[Character] = Field(default_factory=list)
    factions: list[Faction] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    story_threads: list[StoryThread] = Field(default_factory=list)
    canon_events: list[CanonEvent] = Field(default_factory=list)
    sessions: list[Session] = Field(default_factory=list)

    # -- the trust boundary, applied once (AI_ARCHITECTURE.md §12.2, §13) --------

    def trusted(self) -> "CampaignCorpus":
        """Return a copy containing ONLY approved-canon, active material.

        This is the gate every retrieval path passes through. Anything low-trust
        (raw notes never live here to begin with; pending/rejected proposals,
        archived/revised canon, inactive entities) is dropped.
        """
        return CampaignCorpus(
            campaign=self.campaign,
            world_framework=self.world_framework,
            world_entries=[e for e in self.world_entries if e.is_approved_canon],
            characters=[c for c in self.characters if c.status == EntityStatus.active],
            factions=[f for f in self.factions if f.status == EntityStatus.active],
            locations=[l for l in self.locations if l.status == EntityStatus.active],
            # Open/paused threads are live narrative; resolved/abandoned are history.
            story_threads=[
                t for t in self.story_threads
                if t.status in (ThreadStatus.open, ThreadStatus.paused)
            ],
            canon_events=[c for c in self.canon_events if c.status == CanonStatus.active],
            sessions=list(self.sessions),   # summaries only; see chunking below
        )

    # -- offline loader: build a corpus from the synthetic dataset ---------------

    @classmethod
    def from_dataset(cls, data: dict) -> "CampaignCorpus":
        """Build a corpus from the `ashes_kestrel_*` combined dataset shape.

        Tolerant by design: unknown/edge-shaped categories are skipped rather than
        raising, so this stays useful as the sample data evolves. Only the fields
        schemas.py knows about are mapped.
        """
        camp_raw = data.get("campaign") or {}
        campaign = Campaign(
            id=camp_raw.get("campaign_id", "unknown_campaign"),
            name=camp_raw.get("name", "Untitled Campaign"),
            system=camp_raw.get("system"),
            status=camp_raw.get("status"),
            tone=camp_raw.get("tone") or [],
            logline=camp_raw.get("logline"),
        )
        campaign_id = campaign.id

        world = data.get("world") or {}
        world_entries: list[WorldEntry] = []
        for category, block in world.items():
            if not isinstance(block, dict) or "entries" not in block:
                continue  # scalar metadata like world_id/created_date/era
            for e in block.get("entries") or []:
                if not isinstance(e, dict):
                    continue
                world_entries.append(
                    WorldEntry(
                        id=e.get("entry_id", f"{category}_{len(world_entries)}"),
                        campaign_id=campaign_id,
                        category=category,
                        note=e.get("note"),
                        summary=e.get("summary"),
                        entry_tags=e.get("entry_tags") or [],
                        date_created=e.get("date_created"),
                        last_updated=e.get("last_updated"),
                    )
                )

        characters: list[Character] = []
        for pc in data.get("player_characters") or []:
            if not isinstance(pc, dict):
                continue
            characters.append(
                Character(
                    id=pc.get("character_id", f"pc_{len(characters)}"),
                    campaign_id=campaign_id,
                    name=pc.get("name", "Unknown"),
                    kind=CharacterKind.pc,
                    ancestry=pc.get("ancestry"),
                    role=pc.get("role"),
                    current_goal=pc.get("current_goal"),
                    tags=pc.get("active_entry_tags") or [],
                )
            )

        sessions: list[Session] = []
        for s in data.get("sessions") or []:
            if not isinstance(s, dict):
                continue
            sessions.append(
                Session(
                    id=s.get("session_id", f"ses_{len(sessions)}"),
                    campaign_id=campaign_id,
                    session_number=s.get("session_number"),
                    title=s.get("title"),
                    played_at=s.get("played_at"),
                    status=s.get("status"),
                    summary=s.get("summary"),
                    related_entry_ids=s.get("related_entry_ids") or [],
                )
            )

        return cls(
            campaign=campaign,
            world_entries=world_entries,
            characters=characters,
            sessions=sessions,
        )


# =============================================================================
# Chunking — turn trusted source rows into the retrieval index (RagChunk)
# =============================================================================

def chunk_corpus(corpus: CampaignCorpus) -> list[RagChunk]:
    """Flatten a (already-trusted) corpus into retrievable RagChunks.

    Chunk text follows the dataset convention `"<Category>: <text>"` so chunks
    read cleanly on their own. Metadata carries the signals the scorer uses
    (tags, timestamps, importance, source kind). `embedding` stays None in the
    MVP — populated later by an embedding backend (schemas.RagChunk.embedding).
    """
    chunks: list[RagChunk] = []

    for e in corpus.world_entries:
        body = e.summary or e.note
        if not body:
            continue
        label = e.category.replace("_", " ").title()
        chunks.append(
            RagChunk(
                id=f"chunk_{e.id}",
                campaign_id=e.campaign_id,
                category=e.category,
                entry_id=e.id,
                chunk_text=f"{label}: {body}",
                metadata={
                    "source": "world_entry",
                    "entry_tags": e.entry_tags,
                    "date_created": e.date_created.isoformat() if e.date_created else None,
                    "last_updated": e.last_updated.isoformat() if e.last_updated else None,
                },
            )
        )

    for c in corpus.canon_events:
        label = c.category or "General Overview"
        chunks.append(
            RagChunk(
                id=f"chunk_{c.id}",
                campaign_id=c.campaign_id,
                category=label,
                entry_id=c.id,
                chunk_text=f"{label}: {c.summary}",
                metadata={
                    "source": "canon_event",
                    "importance": c.importance.value if c.importance else None,
                    "related_entity_ids": c.related_entity_ids,
                    "date_created": c.created_at.isoformat() if c.created_at else None,
                },
            )
        )

    # Previous session summaries are a trusted retrieval source (§9.1). They are
    # GM-authored/approved recaps, not raw notes — safe to surface as canon-tier.
    for s in corpus.sessions:
        if not s.summary:
            continue
        label = f"Session {s.session_number}" if s.session_number is not None else "Session"
        chunks.append(
            RagChunk(
                id=f"chunk_{s.id}_summary",
                campaign_id=s.campaign_id,
                category="session_summary",
                entry_id=s.id,
                chunk_text=f"{label} — {s.title or ''}: {s.summary}".strip(),
                metadata={
                    "source": "session_summary",
                    "session_number": s.session_number,
                    "date_created": s.played_at.isoformat() if s.played_at else None,
                },
            )
        )

    return chunks


# =============================================================================
# Retriever seam — MVP lexical backend + pgvector skeleton (mirrors llm_provider)
# =============================================================================

class ScoredChunk(BaseModel):
    chunk: RagChunk
    score: float


class Retriever(Protocol):
    """The retrieval interface. Swap the backend, not the callers (§9.3)."""

    name: str

    def index(self, chunks: Iterable[RagChunk]) -> None: ...

    def search(self, query: str, k: int) -> list[ScoredChunk]: ...


class KeywordRetriever:
    """MVP retriever: lexical overlap + recency + importance. No embeddings.

    Deterministic and offline — the retrieval counterpart to `DemoProvider`.
    `index()` pre-tokenises chunks; `search()` ranks them for one query.
    """

    name = "keyword"

    def __init__(self) -> None:
        self._chunks: list[RagChunk] = []
        self._doc_tokens: list[list[str]] = []
        self._recency: list[float] = []          # 0..1, newest = 1
        self._importance: list[float] = []        # 0..1

    def index(self, chunks: Iterable[RagChunk]) -> None:
        self._chunks = list(chunks)
        self._doc_tokens = [tokenize(c.chunk_text) for c in self._chunks]
        self._importance = [
            _IMPORTANCE_BOOST.get(Importance(c.metadata["importance"]), 0.0)
            if c.metadata.get("importance") in {i.value for i in Importance}
            else 0.0
            for c in self._chunks
        ]
        # Recency is relative to the freshest chunk in THIS index, so no wall-clock
        # is needed and ranking is reproducible.
        stamps = [
            _epoch_from_meta(c.metadata) for c in self._chunks
        ]
        known = [s for s in stamps if s is not None]
        if known:
            lo, hi = min(known), max(known)
            span = (hi - lo) or 1.0
            self._recency = [((s - lo) / span) if s is not None else 0.0 for s in stamps]
        else:
            self._recency = [0.0] * len(self._chunks)

    def search(self, query: str, k: int) -> list[ScoredChunk]:
        q = tokenize(query)
        scored: list[ScoredChunk] = []
        for i, chunk in enumerate(self._chunks):
            lexical = _lexical_score(q, self._doc_tokens[i])
            # With no query signal, fall back to recency/importance ordering so a
            # bare "give me context" task still returns the freshest canon.
            total = (
                _W_LEXICAL * lexical
                + _W_RECENCY * self._recency[i]
                + _W_IMPORTANCE * self._importance[i]
            )
            scored.append(ScoredChunk(chunk=chunk, score=total))
        scored.sort(key=lambda sc: sc.score, reverse=True)
        return [sc for sc in scored[:k] if sc.score > 0.0] or scored[:k]


class EmbeddingRetriever:
    """SKELETON for the semantic/hybrid upgrade (AI_ARCHITECTURE.md §9.3).

    Later: embed chunk_text, store vectors in pgvector, and rank by cosine
    similarity (optionally fused with the lexical score above = hybrid search).
    Same interface as KeywordRetriever, so workflows are untouched when it lands.
    """

    name = "embedding"

    def __init__(self, embed_model: str = "text-embedding-3-small") -> None:
        self.embed_model = embed_model

    def index(self, chunks: Iterable[RagChunk]) -> None:
        raise NotImplementedError("EmbeddingRetriever.index — needs pgvector + embeddings")

    def search(self, query: str, k: int) -> list[ScoredChunk]:
        raise NotImplementedError("EmbeddingRetriever.search — needs pgvector + embeddings")


def get_retriever(name: str = "keyword", **kwargs) -> Retriever:
    """Factory selected by config (RAG_RETRIEVER env var). Keeps callers agnostic,
    exactly like llm_provider.get_provider."""
    if name == "keyword":
        return KeywordRetriever()
    if name == "embedding":
        return EmbeddingRetriever(**kwargs)
    raise ValueError(f"unknown retriever: {name}")


def _epoch_from_meta(metadata: dict) -> Optional[float]:
    """Pull the most meaningful timestamp out of a chunk's metadata for recency."""
    from datetime import datetime

    for key in ("last_updated", "date_created"):
        raw = metadata.get(key)
        if not raw:
            continue
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
    return None


# =============================================================================
# Query construction + entity selection
# =============================================================================

def build_query(
    corpus: CampaignCorpus,
    task: JobType,
    raw_note: Optional[str],
    gm_instructions: Optional[str],
) -> str:
    """Assemble the retrieval query text from the task's intent signals.

    - extract_memory: the raw note IS the query — we want canon RELATED to what
      just happened, so the model can flag continuity conflicts. (The note is used
      only to STEER retrieval here; it is never placed in the trusted context.)
    - generate_session_prep: GM focus + the live story-thread titles drive it.
    """
    parts: list[str] = []
    if gm_instructions:
        parts.append(gm_instructions)
    if task == JobType.extract_memory and raw_note:
        parts.append(raw_note)
    # Live threads express "what the campaign is about right now" for either task.
    parts.extend(t.title for t in corpus.story_threads if t.title)
    return " ".join(parts).strip()


def _rank_entities(
    entities: list,
    query_tokens: list[str],
    limit: int,
) -> list[RetrievedEntity]:
    """Rank named entities by lexical relevance to the query; project to the slim
    RetrievedEntity the ContextPackage uses. With no query, preserve input order."""
    def text_of(e) -> str:
        bits = [getattr(e, "name", "") or "", getattr(e, "summary", "") or ""]
        bits.extend(getattr(e, "tags", []) or [])
        bits.extend(getattr(e, "goals", []) or [])
        for attr in ("role", "current_goal", "title"):
            bits.append(getattr(e, attr, "") or "")
        return " ".join(bits)

    scored = [(e, _lexical_score(query_tokens, tokenize(text_of(e)))) for e in entities]
    if query_tokens:
        scored.sort(key=lambda es: es[1], reverse=True)
    chosen = [e for e, _ in scored[:limit]]
    return [
        RetrievedEntity(
            id=e.id,
            name=getattr(e, "name", None) or getattr(e, "title", "") or e.id,
            summary=getattr(e, "summary", None),
        )
        for e in chosen
    ]


# =============================================================================
# Top-level: assemble the ContextPackage (AI_ARCHITECTURE.md §9.4)
# =============================================================================

def assemble_context_package(
    corpus: CampaignCorpus,
    task: JobType,
    *,
    session_id: Optional[str] = None,
    raw_note: Optional[str] = None,
    gm_instructions: Optional[str] = None,
    manual_memories: Optional[str] = None,
    retriever: Optional[Retriever] = None,
    entity_limit: int = DEFAULT_ENTITY_LIMIT,
    canon_limit: int = DEFAULT_CANON_LIMIT,
) -> ContextPackage:
    """Produce the focused, trust-filtered context the prompt builder consumes.

    Steps:
      1. Apply the trust filter (approved canon / active only) — ONCE, up front.
      2. Chunk the trusted canon and rank it for this task's query.
      3. Rank the trusted entities/threads for the same query.
      4. Assemble a ContextPackage, keeping `raw_note` in its own untrusted field.

    This is what `tools.retrieve_relevant_memory` delegates to.
    """
    trusted = corpus.trusted()
    retriever = retriever or get_retriever("keyword")

    query = build_query(trusted, task, raw_note, gm_instructions)
    q_tokens = tokenize(query)

    # Rank the canon (world entries + canon events + session summaries) as chunks.
    retriever.index(chunk_corpus(trusted))
    top = retriever.search(query, canon_limit)
    recent_canon = [
        RetrievedEntity(
            id=sc.chunk.entry_id or sc.chunk.id,
            name=(sc.chunk.category or "canon").replace("_", " ").title(),
            summary=sc.chunk.chunk_text,
        )
        for sc in top
    ]

    return ContextPackage(
        task=task,
        campaign_id=trusted.campaign.id if trusted.campaign else "",
        session_id=session_id,
        world_framework=trusted.world_framework,
        characters=_rank_entities(trusted.characters, q_tokens, entity_limit),
        factions=_rank_entities(trusted.factions, q_tokens, entity_limit),
        locations=_rank_entities(trusted.locations, q_tokens, entity_limit),
        active_story_threads=_rank_entities(trusted.story_threads, q_tokens, entity_limit),
        recent_canon=recent_canon,
        gm_instructions=gm_instructions,
        # Untrusted, and ONLY for extraction — carried as labeled data, never merged
        # into the trusted blocks above (prompt-injection guard, §10.3).
        raw_note=raw_note if task == JobType.extract_memory else None,
        # GM-authored, trusted (unlike raw_note) — specific memories the GM wants
        # the prep to draw from, on top of whatever retrieval finds automatically.
        manual_memories=manual_memories,
    )


__all__ = [
    "CampaignCorpus",
    "RagChunk",
    "ScoredChunk",
    "Retriever",
    "KeywordRetriever",
    "EmbeddingRetriever",
    "get_retriever",
    "chunk_corpus",
    "build_query",
    "tokenize",
    "assemble_context_package",
    "APPROVED_CANON_TAG",
]


# ---------------------------------------------------------------------------
# Offline demo — `python -m backend.rag [path-to-dataset.json]`
# Loads the sample campaign, assembles a prep context package, and prints what
# the model would see. Doubles as a "retrieval preview" (AI_ARCHITECTURE.md §9.4).
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import json
    import sys
    from pathlib import Path

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path(__file__).resolve().parent.parent / "synthetic-data" / "ashes_kestrel_10_session_data_set.json"
    )
    corpus = CampaignCorpus.from_dataset(json.loads(path.read_text()))
    pkg = assemble_context_package(
        corpus,
        JobType.generate_session_prep,
        gm_instructions="Focus on the Salt Guild's tariffs and rising faction tension.",
    )
    print(f"Campaign: {pkg.campaign_id}")
    print(f"Trusted world entries: {len(corpus.trusted().world_entries)} "
          f"(of {len(corpus.world_entries)} total)")
    print(f"\nTop retrieved canon ({len(pkg.recent_canon)}):")
    for item in pkg.recent_canon:
        print(f"  • [{item.name}] {item.summary[:110]}")
    print(f"\nCharacters in context: {[c.name for c in pkg.characters]}")
