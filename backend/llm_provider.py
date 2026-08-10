"""
llm_provider.py — The provider-agnostic LLM seam.

This is the ONE place the rest of the system talks to a foundation model. Workflow
code (the AI-parser, session-prep generator) never imports openai/anthropic directly;
it depends only on the `LLMProvider` interface below. Swapping providers = adding one
adapter class, with zero changes to tools or workflows (AI_ARCHITECTURE.md §4.1, §4.3).

Baseline ships with `DemoProvider` so the entire pipeline runs end-to-end with no API
key and no cost. `OpenAIProvider` is a real adapter behind the same interface;
`AnthropicProvider` is a placeholder for a second one (see docs/KNOWN_LIMITATIONS.md).
"""

from __future__ import annotations

import json
import re
import time
from typing import Protocol

from pydantic import BaseModel

from backend.schemas import WorldCategoryLabel


class LLMRequest(BaseModel):
    """Everything a provider needs for one structured call."""
    system_prompt: str
    user_prompt: str
    prompt_version: str                     # e.g. "note_extraction.v1"
    model_name: str | None = None           # None -> adapter's default
    temperature: float = 0.4
    max_tokens: int = 16000
    # The JSON schema the model must conform to (from a schemas.py model's
    # .model_json_schema()). Adapters use this for structured output / tool-use.
    response_json_schema: dict | None = None


class LLMResponse(BaseModel):
    """Raw result + accounting. The worker validates `raw_text` against the
    expected schemas.py model separately (see tools.validate_structured_output)."""
    raw_text: str                           # the model's JSON string output
    model_provider: str
    model_name: str
    prompt_version: str | None = None       # stamped by tools.call_llm_provider from the request
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: int = 0


class LLMProvider(Protocol):
    """The interface. Mirrors the Go `LLMProvider` in AI_ARCHITECTURE.md §4.1."""

    name: str

    def generate_structured(self, req: LLMRequest) -> LLMResponse:
        ...


# ---------------------------------------------------------------------------
# DemoProvider — deterministic, schema-valid JSON derived from the prompt
# itself. No API key, no network call, no cost. Answers ANY
# note_extraction.v1 / session_prep.v1 / world_bible.v1 / world_expand.v1
# request on its own by reading the labeled sections build_prompt() writes
# into user_prompt (RAW_NOTE_*, GM_FOCUS_*, CANON_*) — enough to exercise the
# full pipeline end-to-end for development/demo purposes.
# ---------------------------------------------------------------------------

def _extract_section(text: str, start: str, end: str) -> str:
    if start not in text or end not in text:
        return ""
    return text.split(start, 1)[1].split(end, 1)[0].strip()


_LABEL_BY_VALUE = {label.value.lower(): label for label in WorldCategoryLabel}

# Keyword fallback for freeform text with no "[Category] Title" marker (e.g. a
# regular session note from the Notes page, not a World Builder submission).
# Demo-quality stand-in for what a real LLM would infer — covers most of the
# 18 categories so the demo provider can exercise more than a handful of them.
_DEMO_KEYWORD_CATEGORY: list[tuple[str, WorldCategoryLabel]] = [
    ("tariff", WorldCategoryLabel.economy), ("tax", WorldCategoryLabel.economy), ("trade", WorldCategoryLabel.economy),
    ("coin", WorldCategoryLabel.economy), ("price", WorldCategoryLabel.economy), ("currency", WorldCategoryLabel.economy),
    ("oath", WorldCategoryLabel.magic_systems), ("magic", WorldCategoryLabel.magic_systems), ("spell", WorldCategoryLabel.magic_systems),
    ("ley", WorldCategoryLabel.magic_systems), ("ritual", WorldCategoryLabel.magic_systems),
    ("court", WorldCategoryLabel.government_organizations), ("council", WorldCategoryLabel.government_organizations),
    ("guard", WorldCategoryLabel.government_organizations), ("kingdom", WorldCategoryLabel.government_organizations),
    ("guild", WorldCategoryLabel.non_government_organizations), ("cult", WorldCategoryLabel.non_government_organizations),
    ("temple", WorldCategoryLabel.non_government_organizations),
    ("law", WorldCategoryLabel.laws), ("ban ", WorldCategoryLabel.laws), ("punish", WorldCategoryLabel.laws),
    ("relic", WorldCategoryLabel.world_artifacts), ("artifact", WorldCategoryLabel.world_artifacts), ("vault", WorldCategoryLabel.world_artifacts),
    ("region", WorldCategoryLabel.regions), ("harbor", WorldCategoryLabel.regions), ("vale", WorldCategoryLabel.regions), ("city", WorldCategoryLabel.regions),
    ("politic", WorldCategoryLabel.politics), ("alliance", WorldCategoryLabel.politics), ("succession", WorldCategoryLabel.politics),
    ("race", WorldCategoryLabel.races), ("ancestry", WorldCategoryLabel.races),
    ("ecosystem", WorldCategoryLabel.ecosystems), ("biome", WorldCategoryLabel.ecosystems), ("weather", WorldCategoryLabel.ecosystems),
    ("cataclysm", WorldCategoryLabel.cataclysmic_events), ("disaster", WorldCategoryLabel.cataclysmic_events),
    ("plague", WorldCategoryLabel.cataclysmic_events), ("flood", WorldCategoryLabel.cataclysmic_events), ("war", WorldCategoryLabel.cataclysmic_events),
    ("technology", WorldCategoryLabel.technology_systems), ("airship", WorldCategoryLabel.technology_systems), ("engine", WorldCategoryLabel.technology_systems),
    ("profession", WorldCategoryLabel.jobs_and_roles), ("caste", WorldCategoryLabel.jobs_and_roles),
    ("era", WorldCategoryLabel.era), ("calendar", WorldCategoryLabel.era),
    ("demograph", WorldCategoryLabel.inhabitants), ("dialect", WorldCategoryLabel.inhabitants), ("commoner", WorldCategoryLabel.inhabitants),
    ("backstory", WorldCategoryLabel.player_characters), ("player character", WorldCategoryLabel.player_characters),
    ("npc", WorldCategoryLabel.npcs), ("merchant", WorldCategoryLabel.npcs),
]


def _guess_category(text: str) -> WorldCategoryLabel:
    lowered = text.lower()
    return next((label for keyword, label in _DEMO_KEYWORD_CATEGORY if keyword in lowered), WorldCategoryLabel.general_overview)


_ENTRY_BLOCK_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.DOTALL)


def _demo_extract_memory(user_prompt: str) -> str:
    note = _extract_section(user_prompt, "RAW_NOTE_START", "RAW_NOTE_END")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", note) if b.strip()]

    proposals = []
    for block in blocks[:10]:
        match = _ENTRY_BLOCK_RE.match(block)
        if match:
            # A World Builder entry: "[Category Label] Title\nnote...\nTags: ...".
            # Use the GM's own category directly — it's authoritative, not a guess.
            label_text, rest = match.group(1), match.group(2)
            category = _LABEL_BY_VALUE.get(label_text.strip().lower(), _guess_category(rest))
            summary = block[:280]
        else:
            category = _guess_category(block)
            summary = block[:280]
        proposals.append(
            {
                "type": "canon_event",
                "category": category.value,
                "proposed_summary": summary,
                "proposed_payload": {},
                "confidence": 0.6,
                "rationale": "Derived from the submitted session note (demo provider — no live LLM call).",
                "potential_conflicts": [],
                "source_note_ids": [],
            }
        )

    if not proposals:
        # No blank-line-separated blocks at all (a single-paragraph freeform
        # note) — fall back to sentence splitting, same as before.
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", note) if s.strip()]
        proposals = [
            {
                "type": "canon_event",
                "category": _guess_category(s).value,
                "proposed_summary": s[:280],
                "proposed_payload": {},
                "confidence": 0.6,
                "rationale": "Derived from the submitted session note (demo provider — no live LLM call).",
                "potential_conflicts": [],
                "source_note_ids": [],
            }
            for s in sentences[:3]
        ]

    return json.dumps({"proposals": proposals})


def _demo_session_prep(user_prompt: str) -> str:
    focus = _extract_section(user_prompt, "GM_FOCUS_START", "GM_FOCUS_END") or "the ongoing story"
    canon_block = _extract_section(user_prompt, "CANON_START", "CANON_END")
    canon_lines = [line.lstrip("- ").strip() for line in canon_block.splitlines() if line.strip()]
    memories = _extract_section(user_prompt, "GM_SELECTED_MEMORIES_START", "GM_SELECTED_MEMORIES_END")

    main_beats = [{"title": "Follow the thread", "description": f"Advance the plot around {focus}.", "related_memory_ids": []}]
    if memories:
        main_beats.insert(0, {"title": "GM-selected focus", "description": f"Build the session around: {memories[:200]}", "related_memory_ids": []})

    return json.dumps(
        {
            "title": f"Session Prep: {focus[:60]}",
            "summary": f"Draft prep focused on {focus}. (Generated by the demo provider, not a live LLM call.)",
            "opening_scene": f"The party regroups, still dealing with the fallout of {focus}.",
            "main_beats": main_beats,
            "npcs": [],
            "faction_moves": canon_lines[:3],
            "encounters": [],
            "clues": canon_lines[3:6],
            "open_questions_for_gm": [f"How should the party respond to {focus}?"],
            "source_memory_ids": [],
        }
    )


_TARGET_CATEGORY_RE = re.compile(r"^\[([^\]]+)\]", re.MULTILINE)
_PROPER_NOUN_RE = re.compile(r"\b([A-Z][a-z]{3,}(?:\s+[A-Z][a-z]{3,})?)\b")
_BIBLE_ENTITY_RE = re.compile(r"^-\s+([^(]+?)\s+\(", re.MULTILINE)


def _demo_world_bible(user_prompt: str) -> str:
    """Two-pass Stage 1 (demo): develop a small, cohesive world bible from the GM's
    entries. Deterministic — seeds named anchors from the entries when present so the
    stand-in feels connected to the GM's input, with evocative fallbacks when sparse."""
    entries = _extract_section(user_prompt, "WORLD_ENTRIES_START", "WORLD_ENTRIES_END")
    tone = next((line.split(":", 1)[1].strip() for line in user_prompt.splitlines() if line.startswith("WORLD_TONE:")), "")

    seen: list[str] = []
    for candidate in _PROPER_NOUN_RE.findall(entries):
        lowered = candidate.lower()
        # Skip world-category labels (e.g. "Politics") and boilerplate — we want
        # real proper nouns as anchors, not the section headers.
        if candidate in seen or lowered in {"tags", "category", "session"} or lowered in _LABEL_BY_VALUE:
            continue
        seen.append(candidate)
    names = seen[:3] or ["The Ashen Concord", "Vaelport", "Mother Sabine"]
    kinds = ["faction", "place", "person"]
    entities = [{"name": name, "kind": kinds[i % 3], "note": "Anchor drawn from the GM's world entries (demo provider)."} for i, name in enumerate(names)]

    bible = {
        "premise": f"A world where {names[0]} holds sway over a land still marked by an old catastrophe, and old bargains bind the living.",
        "tone": tone or "grim, mythic",
        "key_entities": entities,
        "central_tensions": [
            f"{names[0]} tightens its grip while scarcity spreads through the land.",
            "Old oaths bind people to debts they never chose.",
        ],
        "defining_event": "A generation ago a catastrophe reshaped the land and the powers that rule it.",
        "open_questions": [
            "Who truly rules, and by what right?",
            "What was the catastrophe that defines this age?",
            "What does the party owe, and to whom?",
        ],
    }
    return json.dumps(bible)


def _demo_world_expand(user_prompt: str) -> str:
    """Two-pass Stage 2 (demo): expand each requested category into a richer proposal
    that REUSES a bible entity (cross-reference), so the demo world interlocks rather
    than reading as disjointed statements."""
    bible = _extract_section(user_prompt, "WORLD_BIBLE_START", "WORLD_BIBLE_END")
    focus = _extract_section(user_prompt, "GM_FOCUS_START", "GM_FOCUS_END")
    entity_names = [name.strip() for name in _BIBLE_ENTITY_RE.findall(bible)]
    anchor = entity_names[0] if entity_names else "the Ashen Concord"
    other = entity_names[1] if len(entity_names) > 1 else anchor

    proposals = []
    for match in _TARGET_CATEGORY_RE.finditer(focus):
        category = _LABEL_BY_VALUE.get(match.group(1).strip().lower())
        if category is None:
            continue
        summary = (
            f"{category.value}: {anchor} shapes this facet of the world — its institutions, customs, "
            f"and named figures reach into daily life, and its interests collide with {other}. "
            f"This ties directly to the world's central tensions and leaves a hook for play. "
            "(Demo expansion — edit or reject before it becomes canon.)"
        )
        proposals.append(
            {
                "type": "canon_event",
                "category": category.value,
                "proposed_summary": summary,
                "proposed_payload": {"entities": [anchor, other]},
                "confidence": 0.5,
                "rationale": "Expanded from the world bible, cross-referencing established entities (demo provider).",
                "potential_conflicts": [],
                "source_note_ids": [],
            }
        )
    return json.dumps({"proposals": proposals})


class DemoProvider:
    """Deterministic stand-in that needs no canned fixtures and no API key.

    Reads whatever build_prompt() labeled in user_prompt and derives schema-valid
    JSON from it, so `note_extraction.v1` / `session_prep.v1` / `world_bible.v1` /
    `world_expand.v1` requests can be answered for any input. Swap for
    AnthropicProvider / OpenAIProvider later with zero call-site changes.
    """

    name = "demo"

    def generate_structured(self, req: LLMRequest) -> LLMResponse:
        if req.prompt_version == "note_extraction.v1":
            raw_text = _demo_extract_memory(req.user_prompt)
        elif req.prompt_version == "session_prep.v1":
            raw_text = _demo_session_prep(req.user_prompt)
        elif req.prompt_version == "world_bible.v1":
            raw_text = _demo_world_bible(req.user_prompt)
        elif req.prompt_version == "world_expand.v1":
            raw_text = _demo_world_expand(req.user_prompt)
        else:
            raw_text = "{}"
        return LLMResponse(
            raw_text=raw_text,
            model_provider=self.name,
            model_name=req.model_name or "demo-deterministic-v1",
            input_tokens=len(req.system_prompt.split()) + len(req.user_prompt.split()),
            output_tokens=len(raw_text.split()),
            estimated_cost_usd=0.0,
            latency_ms=1,
        )


# ---------------------------------------------------------------------------
# Real adapters — SKELETONS. Implement when a provider is chosen (D-provider).
# ---------------------------------------------------------------------------

class AnthropicProvider:
    """TODO: implement with the Anthropic SDK (recommended default).
    Use tool-use / structured output for reliable JSON; map usage -> tokens/cost."""

    name = "anthropic"

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-5") -> None:
        self.api_key = api_key
        self.default_model = default_model

    def generate_structured(self, req: LLMRequest) -> LLMResponse:
        raise NotImplementedError("AnthropicProvider.generate_structured")


# Model routing by task (SOFTWARE_ARCHITECTURE.md §8.4.2): cheaper model for the
# extraction workflow (runs after every session), stronger model for prep (the
# GM actually reads this). Falls back to the extraction model for anything else.
_MODEL_BY_PROMPT_VERSION = {
    "note_extraction.v1": "gpt-4o-mini",
    "session_prep.v1": "gpt-4o",
}

# Approximate list pricing, USD per 1K tokens (input, output). Rough estimates
# for the cost-visibility tile, not a billing source of truth — update if
# OpenAI's pricing changes or you swap models.
_PRICE_PER_1K_TOKENS_USD = {
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
}


class OpenAIProvider:
    """Real adapter over the OpenAI Chat Completions API.

    Requests that carry ``response_json_schema`` use JSON-object mode, with the
    schema also embedded in the prompt. Requests without a schema return normal
    text; the evaluation baseline uses this path to generate a Markdown world
    document. Product workflows always attach a schema, so this preserves their
    structured-output contract.
    """

    name = "openai"

    def __init__(self, api_key: str, default_model: str = "gpt-4o-mini") -> None:
        if not api_key:
            raise ValueError("OpenAIProvider requires a non-empty api_key")
        self.api_key = api_key
        self.default_model = default_model
        self._client = None  # lazily constructed so import is only needed when used

    def _client_or_create(self):
        if self._client is None:
            from openai import OpenAI
            # An explicit timeout matters here: without one, a request whose
            # socket dies silently (e.g. the machine sleeps mid-call) can hang
            # forever instead of raising, since nothing else in this codebase
            # bounds how long a call is allowed to take. 300s (not 120s): a
            # genuinely large max_tokens=16000 completion (e.g. verdicting a
            # few hundred gold facts) can legitimately take longer than 120s
            # to finish generating, not just to fail.
            self._client = OpenAI(api_key=self.api_key, timeout=300.0)
        return self._client

    def generate_structured(self, req: LLMRequest) -> LLMResponse:
        client = self._client_or_create()
        model_name = req.model_name or _MODEL_BY_PROMPT_VERSION.get(req.prompt_version, self.default_model)

        user_prompt = req.user_prompt
        if req.response_json_schema:
            user_prompt += (
                "\n\nOUTPUT_JSON_SCHEMA:\n"
                + json.dumps(req.response_json_schema)
                + "\nRespond with a single JSON object conforming exactly to this schema. No prose, no markdown fences."
            )

        started = time.monotonic()
        request_args = dict(
            model=model_name,
            messages=[
                {"role": "system", "content": req.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        if req.response_json_schema:
            request_args["response_format"] = {"type": "json_object"}
        completion = client.chat.completions.create(**request_args)
        latency_ms = int((time.monotonic() - started) * 1000)

        raw_text = completion.choices[0].message.content
        if not raw_text:
            raise ValueError("OpenAI response contained no content")

        usage = completion.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        input_price, output_price = _PRICE_PER_1K_TOKENS_USD.get(model_name, (0.0, 0.0))
        estimated_cost_usd = (input_tokens / 1000) * input_price + (output_tokens / 1000) * output_price

        return LLMResponse(
            raw_text=raw_text,
            model_provider=self.name,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
            latency_ms=latency_ms,
        )


def get_provider(name: str, **kwargs) -> LLMProvider:
    """Factory selected by config (LLM_PROVIDER env var). Keeps callers agnostic."""
    if name == "demo":
        return DemoProvider(**kwargs)
    if name == "anthropic":
        return AnthropicProvider(**kwargs)
    if name == "openai":
        return OpenAIProvider(**kwargs)
    raise ValueError(f"unknown LLM provider: {name}")
