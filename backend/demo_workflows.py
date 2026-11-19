"""Deterministic offline fixtures, isolated from SQL-backed AI workflows.

Real providers are explicitly rejected in offline mode; these fixtures must never
silently substitute for a live provider selected by the user.
"""
from typing import Any
from uuid import uuid4
import re
from backend.schemas import WorldCategoryLabel


def _id(prefix):
    return f'{prefix}_{uuid4().hex[:12]}'


def _proposal_from_notes(content: str, source: str) -> list[dict[str, Any]]:
    lowered = content.lower()
    matches = [
        ("tax", "Economy", "A change to taxes, tariffs, or trade was reported."),
        ("tariff", "Economy", "A change to taxes, tariffs, or trade was reported."),
        ("oath", "Magic Systems", "An oath or magical rule was reported."),
        ("magic", "Magic Systems", "A magical event or rule was reported."),
        ("court", "Government Organizations", "A government organization changed or acted."),
        ("faction", "Non-Government Organizations", "A faction action was reported."),
    ]
    unique: dict[str, tuple[str, str]] = {}
    for word, category, title in matches:
        if word in lowered:
            unique.setdefault(category, (title, category))
    if not unique:
        unique["General Overview"] = ("A new campaign event was reported.", "General Overview")
    return [
        {
            "id": _id("proposal"), "title": title, "category": category, "confidence": "Medium",
            "summary": content.strip()[:500], "source": source, "status": "pending", "conflicts": [],
            "promptVersion": "note_extraction.v1",
        }
        for title, category in unique.values()
    ]



def _inmemory_build_proposals(campaign_name: str, entries_note: str, expand_labels: list[str]) -> list[dict[str, Any]]:
    """Richer in-memory stand-in mirroring the two-pass worker: derive a shared
    anchor (so proposals cross-reference), then one proposal per expand category.
    The Postgres path uses the real worker (bible -> expansion)."""
    label_values = {label.value.lower() for label in WorldCategoryLabel}
    nouns = re.findall(r"\b([A-Z][a-z]{3,}(?:\s+[A-Z][a-z]{3,})?)\b", entries_note)
    anchor = next((noun for noun in nouns if noun.lower() not in label_values), None) or campaign_name
    proposals: list[dict[str, Any]] = []
    for label in expand_labels:
        summary = (
            f"{label}: {anchor} shapes this facet of the world — named institutions and figures reach into "
            f"daily life, tied to the world's central tensions and leaving a hook for play. "
            "(Demo build — edit or reject before it becomes canon.)"
        )
        proposals.append({
            "id": _id("proposal"),
            "title": f"{label} — {anchor}",
            "category": label,
            "confidence": "Medium",
            "summary": summary,
            "source": "World build",
            "status": "pending",
            "conflicts": [],
            "promptVersion": "world_expand.v1",
        })
    return proposals

