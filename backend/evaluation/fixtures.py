"""
evaluation/fixtures.py — A demo provider so the whole pipeline runs OFFLINE.

The product's `DemoProvider` (backend/llm_provider.py) derives schema-valid JSON
from whatever build_prompt() labeled in the prompt text — great for exercising the
product's own workflows, but not enough to exercise the evaluation end-to-end
(which needs generation, gold extraction, fact checks, judging, and disagreement
discussion to all return coherent, related JSON).

This module's `DemoProvider` fills that gap. It is DETERMINISTIC and
dependency-free: given the prompt_version and the prompt text, it returns
believable, self-consistent output so `python -m backend.evaluation.run_evaluation`
produces a real-looking report with NO API key and NO cost. Swap it for a real
provider to run a real experiment.

Nothing here is used in a real run — it exists purely to demonstrate the harness.
The demo is rigged so the "our_system" documents are higher quality than the
"baseline" documents, and so at least one evaluator disagreement is triggered, so
every section of the report has something to show.
"""

from __future__ import annotations

import hashlib
import json
import re

from backend.llm_provider import LLMResponse


def _h(*parts: str) -> int:
    """Stable non-negative hash (so demo choices are deterministic across runs)."""
    digest = hashlib.sha256("::".join(parts).encode()).hexdigest()
    return int(digest[:8], 16)


# --- Canned world documents, tagged with a machine-readable quality TIER ------

def _world_doc(tier: str, run_index: int) -> str:
    """A canned world document. The TIER marker is read back by the demo judge /
    fact-checker so scores stay consistent with document quality."""
    if tier == "high":
        body = (
            "## Overview\nKestrel Vale is a drowned river valley where law and salt "
            "trade entangle. The drowned bell tolls as both omen and taboo.\n\n"
            "## Locations\n- Kestrel Gate — toll-choked bridge city.\n"
            "## Factions & Organizations\n- Iron Court; Salt Guild; Bridge Wardens "
            "(now split into loyalists and reformers).\n"
            "## Characters\n- Talon Ashvale (PC), Ser Caldus (NPC warden).\n"
            "## Events (chronological)\nAsh rain at Kestrel Gate; tariffs exposed; "
            "wardens fracture after Ser Caldus refuses an unlawful order.\n"
            "## Relationships\nSer Caldus ↔ Bridge Wardens (catalyst of the split); "
            "Salt Guild ↔ tariffs.\n## Open Threads\nSource of the ash-scar pact."
        )
    else:
        body = (
            "# Kestrel Vale\nA valley with a bridge and some guilds. The party did "
            "things across several sessions. There was ash and a bell. Also a "
            "dragon awakened beneath the gate and burned the Iron Court to ash."  # invented
        )
    return f"<!--TIER:{tier} RUN:{run_index}-->\n{body}\n\n_(run {run_index})_"


# --- Handlers per prompt_version ----------------------------------------------

def _handle_generation(prompt_version: str) -> str:
    run = 0
    m = re.search(r"#run(\d+)", prompt_version)
    if m:
        run = int(m.group(1))
    tier = "high" if prompt_version.startswith("our_system_worldbuild") else "low"
    return _world_doc(tier, run)


def _handle_gold_extraction() -> str:
    # A fixed, believable gold set (ids get reassigned by extract_gold_facts).
    facts = [
        {"text": "The party arrived at Kestrel Gate during unnatural ash rain.", "kind": "fact",
         "entities": ["Kestrel Gate"], "importance": "major"},
        {"text": "Bridge tariffs are crushing commoners.", "kind": "fact",
         "entities": ["Bridge Wardens"], "importance": "major"},
        {"text": "The drowned bell is both religious warning and political taboo.", "kind": "fact",
         "entities": ["drowned bell"], "importance": "normal"},
        {"text": "Bridge wardens split into Iron Court loyalists and reformers.", "kind": "fact",
         "entities": ["Bridge Wardens", "Iron Court"], "importance": "critical"},
        {"text": "Ser Caldus refused an unlawful order.", "kind": "fact",
         "entities": ["Ser Caldus"], "importance": "major"},
        {"text": "Talon Ashvale seeks the source of his ash-scar pact.", "kind": "fact",
         "entities": ["Talon Ashvale"], "importance": "normal"},
        {"text": "The Salt Guild controls salt access in the valley.", "kind": "fact",
         "entities": ["Salt Guild"], "importance": "normal"},
        {"text": "Ser Caldus's refusal caused the warden fracture.", "kind": "relationship",
         "entities": ["Ser Caldus", "Bridge Wardens"], "importance": "major"},
        {"text": "The Salt Guild is tied to the tariff regime.", "kind": "relationship",
         "entities": ["Salt Guild", "Bridge Wardens"], "importance": "normal"},
        {"text": "Talon Ashvale is a player character in the valley campaign.", "kind": "relationship",
         "entities": ["Talon Ashvale", "Kestrel Vale"], "importance": "normal"},
    ]
    return json.dumps({"facts": facts})


def _parse_tier(text: str) -> str:
    m = re.search(r"<!--TIER:(\w+)", text)
    return m.group(1) if m else "low"


def _split_ids(user_prompt: str) -> tuple[list[str], list[str]]:
    """Pull fact ids and relationship ids out of the fact-check prompt."""
    parts = user_prompt.split("(B) GROUND-TRUTH RELATIONSHIPS:")
    facts_block = parts[0]
    rel_block = parts[1] if len(parts) > 1 else ""
    # Relationship block also precedes "(C) CANDIDATE DOCUMENT"; trim it.
    rel_block = rel_block.split("(C) CANDIDATE DOCUMENT")[0]
    fact_ids = re.findall(r"\[(fact_\d+)\]", facts_block)
    rel_ids = re.findall(r"\[(fact_\d+)\]", rel_block)
    # A fact id may appear in both blocks; keep relationships out of the fact list.
    fact_ids = [i for i in fact_ids if i not in set(rel_ids)]
    return fact_ids, rel_ids


def _handle_fact_check(user_prompt: str) -> str:
    tier = _parse_tier(user_prompt)
    fact_ids, rel_ids = _split_ids(user_prompt)
    preserve_pct = 95 if tier == "high" else 55
    n_contradict = 0 if tier == "high" else 2
    n_unsupported = 1 if tier == "high" else 3

    fact_verdicts, contradicted_used = [], 0
    for fid in fact_ids:
        if _h(fid, tier) % 100 < preserve_pct:
            fact_verdicts.append({"gold_fact_id": fid, "status": "preserved",
                                  "evidence": "stated in the document"})
        elif contradicted_used < n_contradict:
            contradicted_used += 1
            fact_verdicts.append({"gold_fact_id": fid, "status": "contradicted",
                                  "evidence": "document asserts the opposite"})
        else:
            fact_verdicts.append({"gold_fact_id": fid, "status": "missing",
                                  "evidence": "not mentioned"})

    unsupported = []
    if tier != "high":
        unsupported.append({"statement": "A dragon awakened beneath the gate and burned the Iron Court.",
                            "why": "no session note supports this"})
    for k in range(n_unsupported - len(unsupported)):
        unsupported.append({"statement": f"Unsupported embellishment #{k+1}.",
                            "why": "not grounded in the notes"})

    rel_verdicts = []
    for rid in rel_ids:
        correct = (tier == "high") or (_h(rid, "rel", tier) % 3 == 0)
        rel_verdicts.append({"gold_fact_id": rid, "correct": correct,
                             "evidence": "relationship present" if correct else "relationship wrong/absent"})

    return json.dumps({
        "fact_verdicts": fact_verdicts,
        "unsupported_claims": unsupported,
        "relationship_verdicts": rel_verdicts,
    })


def _handle_judge(user_prompt: str, strictness: int) -> str:
    tier = _parse_tier(user_prompt)
    base = (
        {"depth_completeness": 5, "internal_consistency": 5,
         "logical_coherence": 5, "faithfulness_to_notes": 5}
        if tier == "high" else
        {"depth_completeness": 2, "internal_consistency": 3,
         "logical_coherence": 2, "faithfulness_to_notes": 3}
    )
    scores = []
    for key, val in base.items():
        s = val - strictness
        # Strict persona is extra harsh on faithfulness for low-tier docs — this
        # deliberately manufactures a >=2 spread so the report's disagreement
        # deep-dive section has a case to show.
        if key == "faithfulness_to_notes" and tier != "high" and strictness > 0:
            s -= 1
        s = max(1, min(5, s))
        scores.append({
            "criterion_key": key,
            "score": s,
            "justification": f"[demo] {tier}-tier document; scored {s} on {key}.",
        })
    comment = "Strong, faithful, well-structured." if tier == "high" else \
              "Thin and drifts from the notes in places."
    return json.dumps({"criterion_scores": scores, "overall_comment": comment})


def _handle_discussion() -> str:
    return json.dumps({
        "discussion": (
            "[demo] The gap reflects differing strictness on faithfulness: the "
            "harsher evaluator penalized an invented detail the other treated as "
            "harmless color. The stricter reading is better supported here because "
            "the invented claim has no basis in the notes. A human should confirm "
            "whether the disputed passage is grounded before settling the score."
        )
    })


class DemoProvider:
    """Deterministic offline provider. `strictness` gives each judge a distinct
    persona so inter-evaluator agreement is a real (non-trivial) number."""

    def __init__(self, name: str = "demo", strictness: int = 0) -> None:
        self.name = name
        self.strictness = strictness

    def generate_structured(self, req) -> LLMResponse:  # noqa: ANN001 (duck-typed LLMProvider)
        pv = req.prompt_version
        if pv.startswith(("baseline_worldbuild", "our_system_worldbuild")):
            raw = _handle_generation(pv)
        elif pv.startswith("eval_gold_extraction"):
            raw = _handle_gold_extraction()
        elif pv.startswith("eval_fact_check"):
            raw = _handle_fact_check(req.user_prompt)
        elif pv.startswith("eval_judge_qualitative"):
            raw = _handle_judge(req.user_prompt, self.strictness)
        elif pv.startswith("eval_disagreement_discussion"):
            raw = _handle_discussion()
        else:
            raw = "{}"
        return LLMResponse(
            raw_text=raw,
            model_provider=self.name,
            model_name=req.model_name or f"{self.name}-model",
        )


__all__ = ["DemoProvider"]
