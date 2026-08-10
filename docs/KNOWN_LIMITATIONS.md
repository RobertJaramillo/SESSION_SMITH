# Known Limitations & Future Expansion Notes

A working reference for gaps, stubs, and boundaries discovered while building and testing the
AI Campaign Orchestration platform — what's intentionally not built yet, what works but has a
real ceiling, and what to revisit as the system scales. Update this file as new limitations are
found or existing ones are resolved; it should stay a living, accurate reference, not a changelog.

## Stubs — not implemented, but inert (safe for a proof of concept)

These exist as placeholders with a defined interface but no working implementation. None of them
are silently degrading behavior today — nothing in the running system calls them unless explicitly
configured to, and nothing is configured to.

- **`AnthropicProvider`** (`backend/llm_provider.py`) — `generate_structured` raises
  `NotImplementedError`. Only reachable if `LLM_PROVIDER=anthropic` is explicitly set; nothing
  defaults to it. Today only `demo` (offline, deterministic) and `openai` are real.
- **`EmbeddingRetriever`** (`backend/rag.py`) — `index`/`search` both raise `NotImplementedError`.
  All retrieval today goes through `KeywordRetriever` (lexical/TF-based). The `get_retriever()`
  call site hardcodes `"keyword"`; the `RAG_RETRIEVER` env var mentioned in a docstring is
  **not actually read anywhere** — it's aspirational documentation, not a real config knob.
- **Authentication** — sign-in is a mocked client-side gate (any submit authenticates). No real
  session/auth layer exists yet (see `CLAUDE.md`).
- **`world_frameworks` / `characters` / `factions` / `locations` / `story_threads` tables** — no API
  endpoint writes to any of them. World-building only ever produces `world_entries` and
  `canon_events`. The RAG corpus still queries all five (in case a future writer lands), so they're
  always empty/`None` in `ContextPackage` today — none of them contribute anything to retrieval or
  prompts yet (e.g. `WORLD_TONE` never appears in a prompt, because no `world_frameworks` row ever
  exists to read it from).

## Design-doc goals not (fully) realized

Unlike the stubs above, these aren't labeled `NotImplementedError` anywhere — the surrounding code
runs and looks complete, but a specific capability `AI_ARCHITECTURE.md` describes silently doesn't
do anything. Worth flagging distinctly because nothing surfaces these as incomplete at runtime.

- **"Identify changes to characters, factions, locations, and story threads" (§3.1, goal 4) is only
  half-built.** The model does classify each proposal's `type` as one of `canon_event`,
  `character_update`, `faction_update`, `location_update`, `story_thread_update` (see
  `_TYPE_GUIDANCE` in `backend/tools/prompting.py`), and that value is stored. But
  `ProposalRepository.review()` (`backend/repositories/proposals.py`) doesn't read `type` at all —
  approving *any* proposal, regardless of type, always writes a flat `canon_events` row. There is no
  code path that ever creates or updates a row in `characters`/`factions`/`locations`/
  `story_threads`, so "identify changes to X" only goes as far as labeling the change, never
  structurally applying it to X.
- **No retrieval-preview/debug endpoint.** §9.4 of the design doc calls for the assembled context
  package to be "inspectable through a retrieval preview endpoint so developers can debug what the
  model sees." No such endpoint exists — the only way to inspect what a prompt actually retrieved is
  to call `retrieve_relevant_memory` directly in a Python shell (as done ad hoc during this session's
  testing), not through the API.
- **MVP retrieval doesn't use PostgreSQL full-text search**, which §9.2 lists as one MVP option.
  `KeywordRetriever` (`backend/rag.py`) implements an equivalent in-process Python TF-weighted scorer
  instead of Postgres `tsvector`/`ts_rank`. Functionally similar (both are lexical, not semantic), but
  worth knowing it's not literally what §9.2 describes — everything is ranked in the API process, not
  the database.

## Known limitations — working, but with a real ceiling

- **Retrieval is keyword/lexical, not semantic** (`KeywordRetriever` in `backend/rag.py`, TF-weighted
  overlap). It can miss conceptually-relevant canon that uses different vocabulary than the query
  (e.g. a note about "taxes" won't necessarily surface canon written around "tariffs"). Mitigated
  today by setting `DEFAULT_CANON_LIMIT = 40` so most/all of a campaign's canon is included rather
  than aggressively ranked down — current campaign sizes (a two-pass build is ~18-40 canon events)
  stay comfortably under that. **This stops helping once a campaign's canon significantly exceeds
  ~40 entries** — at that point, either raise the limit further (token/cost tradeoff) or implement
  `EmbeddingRetriever` for real (needs an embedding model call + `pgvector` + a migration to backfill
  existing canon — a real infrastructure project, not a config change).
- **World-build category coverage is bounded, not absolute.** The two-pass generator
  (`world_bible.v1` → `world_expand.v1`, `backend/worker.py`) batches categories (`_EXPAND_BATCH_SIZE
  = 5`) and retries whatever a batch skips in shrinking passes, capped at `_MAX_EXPAND_PASSES = 4`.
  This is a strong practical guarantee, observed to reliably reach 18/18, but not a mathematical one
  — a pathological category could still come back missing after 4 passes. The GM's mitigation is
  **Regenerate**.
- **`gpt-4o-mini` under-complies with "cover every item in this list" instructions**, even well
  within its available token budget — this was the root cause behind the world-build coverage gap
  (confirmed via real usage data: 359 of 4000 output tokens used, 2 of 18 categories attempted, no
  error). This is a general characteristic of that model, not specific to world-building — any future
  prompt that asks for exhaustive coverage of a list should assume it needs the same batching/retry
  treatment, not just a longer prompt.
- **`max_tokens` is a single fixed default (16000)** on `LLMRequest` (`backend/llm_provider.py`), not
  tuned per prompt version. `gpt-4o-mini`'s actual API-side ceiling is 16,384 output tokens, so this
  default leaves almost no headroom — any prompt version that legitimately needs more per call (larger
  batches, longer required summaries) will hit the model's hard ceiling, not just this default, and
  will need real batching/retry treatment rather than a larger `max_tokens` value.
- **Conflict/grounding detection (`potential_conflicts`) is prompt-driven, not independently verified.**
  The note-extraction system prompt (`_CONFLICT_GUIDANCE`, `backend/tools/prompting.py`) asks the model
  to flag two things into the same `potential_conflicts` list: contradictions with retrieved canon, and
  claims in `proposed_summary` it can't ground in the source `RAW_NOTE`. This is now surfaced in the
  Review Queue (`ApiProposal.conflicts`, rendered by `ProposalCard` in `frontend/src/App.tsx`), but
  detection still depends entirely on the live model noticing and self-reporting the issue — there is
  no independent verification pass (e.g. a second grounding-check call), and this hasn't been validated
  against a real OpenAI run.
- **Session Prep generation itself has not been stress-tested the way World Builder was.** The
  approval lifecycle around it (`session_preps.status`/`approved_outline`/`approved_at`, migration
  `006_session_preps_approval.sql`; `POST /v1/campaigns/{campaign_id}/session-prep/approve`) is
  implemented and covered by tests, but the actual `session_prep.v1` output hasn't been checked for
  the same class of issues that hit world-building — token budget, list-coverage under-compliance,
  retrieval quality against a large canon corpus. Unconfirmed either way; watch for it if a campaign's
  canon grows large.
- **Pushing `extract_memory` toward higher-granularity extraction was tried and reverted — it has a
  real precision/consistency tradeoff, not a free win.** A real 51-session run compared prompting the
  model to extract every discrete fact per note (vs. its default of a couple of compressed bullets per
  note) against an unmodified baseline. Proposal volume rose ~2.6x (139 → 357 canon entries), but the
  qualitative rubric moved from a tie with a ChatGPT baseline to a clear loss, and `unsupported_facts`
  nearly tripled (9.0 → 13.5). Two causes, confirmed by inspection: (1) the eval's `unsupported_facts`
  metric checks against a separately-extracted, lossy gold-fact list, not the raw notes directly — a
  spot-checked "unsupported" claim was genuinely grounded in the raw note, just absent from that
  smaller reference list, so higher real recall gets partly misread as invention; (2) judges' own
  justifications explicitly cited repetition/redundancy ("the repeated mention of 'outstanding plot
  threads' could lead to confusion") hurting Internal Consistency and Logical Coherence — the
  redundancy-avoidance instruction added alongside the granularity push wasn't strong enough to keep
  up with the 2.6x volume increase. If revisited, isolate the "don't invent" drafting-rule change from
  the granularity push and test each independently, and pair any granularity increase with a stronger
  (not just prompted) deduplication mechanism.
- **Canon has no temporal supersession, even though the data model already anticipated it.**
  `CanonStatus` (`backend/schemas.py:136-139`) defines `revised` and `archived` alongside `active`, and
  `ProposalStatus` (`backend/schemas.py:94`) separately defines `superseded` — but no code path anywhere
  sets either to anything but the default. `rag.py`'s `CampaignCorpus.trusted()` (`backend/rag.py:182`)
  already filters retrieval to `status == active`, ready to exclude revised/archived canon — the missing
  piece is upstream: nothing in `review_proposal`/`worker.py` ever marks an OLDER canon entry as
  revised/archived when a NEWER, conflicting one about the same evolving property (character level,
  location, faction control, item possession) gets approved. Every approved fact just accumulates as
  `active` forever, so a campaign's canon can hold several simultaneously-"true" snapshots of the same
  property from different points in the story, with nothing recorded to say which one is current.

  This is not hypothetical — it's exactly what broke the evaluation pipeline's `contradictions` metric
  (`backend/evaluation/fact_checks.py`, `_FACT_CHECK_SYSTEM_PROMPT`): gold facts extracted from a
  51-session campaign included "the party leveled up to level 2," "...level 4," and "...level 5" as
  three separate, equally-"true" facts with no ordering between them, so a document correctly stating
  the LATEST level got flagged as contradicting an EARLIER snapshot. A mitigation was tried at the
  *consumption* layer (the eval script): `_format_gold_for_prompt` now labels each fact with its session
  order, and `_FACT_CHECK_SYSTEM_PROMPT` explicitly instructs the judge that a later-session state isn't a
  contradiction of an earlier one. On a follow-up run, the SAME level-progression contradiction was still
  flagged even with that ordering explicit in the prompt — so this is not confirmed to be a reliable fix,
  only a plausible one. The underlying gap is that canon itself has no notion of "this fact superseded
  that one," and resolving that likely needs to happen at the *source* (when canon is written), not by
  asking a per-fact judge call to reason about ordering correctly every time.

  A real fix needs: (1) at approval time, detecting when a new canon entry's category/entities match an
  existing active entry describing the same evolving property (the existing `potential_conflicts`
  mechanism, see above, flags contradictions today but doesn't resolve them into a status change); (2) a
  GM-facing decision at that point (revise / keep both / archive the old one); (3) actually writing the
  resulting transition to `canon_events`. This is a real design + implementation project — closer in
  scope to the `EmbeddingRetriever` gap above than to a config change — not something to patch quickly.

## Recently fixed (for context — these are resolved, not open)

- Session Prep's "Use memories" field was accepted by the API and silently discarded —
  `worker.generate_session_prep` never read it, so GMs had no way to steer which specific memories a
  prep drew from (the design doc's "manual GM-selected context" retrieval source, §9.2) → wired
  through as a new, trusted `GM_SELECTED_MEMORIES` prompt block; `session_prep.v1` also gained its own
  system prompt (it previously fell through to the extraction prompt, which references `category`/
  `type`/conflict fields the session-prep schema doesn't have). Leaving the field blank behaves
  exactly as before — no block is added to the prompt.
- World-build output was flat, generic, one-sentence-per-category, and disjointed → replaced with a
  two-pass generator (world bible → grounded, cross-referencing expansion).
- World-build silently covered only a few of 18 categories, well within token budget (a model
  instruction-following gap, not truncation) → fixed via category batching + bounded multi-pass retry.
- A live OpenAI response occasionally put a category slug (e.g. `"magic_system"`) in the proposal
  `type` field, failing strict schema validation → now tolerantly coerced to a safe default instead
  of failing the whole batch.
- **Canon carried no provenance, so an evaluation run scored World-Builder-invented lore as a
  faithfulness failure.** `canon_events`/`CanonEvent` already had `model_provider`/`model_name`/
  `prompt_version`/`created_by_job_id`/`schema_version` columns, but `ProposalsRepository.review()`
  never populated them on approval, and `list_canon()` never read them back — so nothing distinguished
  faithful `extract_memory()` canon from deliberately creative `build_world()` canon (see
  `AI_ARCHITECTURE.md` §6). An evaluation run scored a real exported world document (mixing both) for
  faithfulness against session-note gold facts and, unsurprisingly, penalized the World-Builder content
  it was never trying to make faithful. Fixed by populating those columns at write time, deriving an
  `origin` (`schemas.classify_canon_origin()`) from `prompt_version` at read time, and adding
  `?scope=session_notes` to `GET /v1/campaigns/{id}/world-export` so the evaluation pipeline can request
  a faithfulness-scoped export instead of the full one (see `backend/evaluation/README.md`).
- World Builder's "Seal world" button (and therefore PDF/Markdown export, which only appears once
  sealed) disappeared once every proposal was approved, because both were gated on
  `pendingProposals.length > 0` → decoupled; Seal World now shows whenever the world has any built
  content, independent of pending count.
- Canon retrieved into extraction/expansion prompts showed a generic "Canon Event" label instead of
  its real world category, because the `CanonEvent` model didn't carry a `category` field even
  though the database row does → fixed.
- Canon retrieval was capped at 8 chunks regardless of corpus size, silently dropping most of a
  freshly-built 18-40-entry world → raised to 40 (see "Known limitations" above for the ceiling this
  doesn't solve).
