"""World export — assemble a campaign's world into a Markdown document.

Used to evaluate the system's output. Pure formatting over already-stored data
(the GM's world_entries + approved canon_events); no AI/LLM call, so it is $0 and
safe to run repeatedly. The Markdown is rendered to PDF by
scripts/render_markdown_pdf.py at the API edge.

Document order:
  1. World Overview  — the General Overview category (user entries + canon).
  2. Information provided when creating the world — the GM's original entries.
  3. Canon by category — approved canon.
  4. Planned Next Session (optional) — the GM's approved session prep, if any.
     NOT canon — nothing here came from approved session notes or world-building;
     it's a plan for a session that hasn't been played yet.
Everything after the overview is grouped by the 18 categories in canonical order.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Optional, Sequence

from backend.schemas import WorldCategoryLabel

_OVERVIEW = WorldCategoryLabel.general_overview


def _to_label(value: str) -> Optional[WorldCategoryLabel]:
    """Normalize a stored category to a WorldCategoryLabel.

    Entries store the snake_case id ("economy"); canon stores the label
    ("Economy"). Accept either; ignore anything unrecognized.
    """
    if not value:
        return None
    try:
        return WorldCategoryLabel(value)  # label form, e.g. "Economy"
    except ValueError:
        pass
    key = value.strip().lower()
    return WorldCategoryLabel[key] if key in WorldCategoryLabel.__members__ else None


def _group(rows: Sequence[Mapping[str, Any]]) -> dict[WorldCategoryLabel, list[Mapping[str, Any]]]:
    grouped: dict[WorldCategoryLabel, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        label = _to_label(str(row.get("category", "")))
        if label is not None:
            grouped[label].append(row)
    return grouped


def build_world_export_markdown(
    campaign_name: str,
    entries: Sequence[Mapping[str, Any]],
    canon: Sequence[Mapping[str, Any]],
    next_session_plan: Optional[str] = None,
    origin_filter: Optional[str] = None,
) -> str:
    """Assemble the world-export Markdown.

    `entries`: rows with {category, title, note}. `canon`: rows with {category,
    summary, origin}, where `origin` (see `schemas.classify_canon_origin`) is
    "session_notes" (faithful extraction), "world_builder" (deliberately
    creative — see AI_ARCHITECTURE.md §6), or "unknown" (pre-dates provenance
    tracking). `next_session_plan`: the GM's approved (possibly edited)
    session-prep outline text, if any — rendered as a separate, explicitly
    non-canon section.

    `origin_filter`: when set, only canon rows whose `origin` matches are
    included. Used by the evaluation pipeline to score a faithfulness-scoped
    export (`origin_filter="session_notes"`) without World-Builder-invented
    lore skewing the comparison against session notes. The default (`None`)
    keeps the GM-facing export showing everything they approved.
    """
    if origin_filter is not None:
        canon = [c for c in canon if c.get("origin") == origin_filter]
    entries_by = _group(entries)
    canon_by = _group(canon)

    lines: list[str] = [f"# {campaign_name} — World Export", ""]

    # 1. World Overview — the General Overview category.
    lines += ["## World Overview", ""]
    overview = [f"- {e.get('title', '')}: {e.get('note', '')}" for e in entries_by.get(_OVERVIEW, [])]
    overview += [f"- {c.get('summary', '')}" for c in canon_by.get(_OVERVIEW, [])]
    lines += overview or ["No overview provided."]
    lines += [""]

    # 2. Information provided when creating the world — the GM's entries.
    lines += ["## Information provided when creating the world", ""]
    wrote_entries = False
    for label in WorldCategoryLabel:
        if label is _OVERVIEW:
            continue
        items = entries_by.get(label, [])
        if not items:
            continue
        wrote_entries = True
        lines.append(f"**Category: {label.value}**")
        lines += [f"- {e.get('title', '')}: {e.get('note', '')}" for e in items]
        lines.append("")
    if not wrote_entries:
        lines += ["No world-build entries were recorded.", ""]

    # 3. Canon by category — approved canon.
    lines += ["## Canon by category", ""]
    wrote_canon = False
    for label in WorldCategoryLabel:
        if label is _OVERVIEW:
            continue
        items = canon_by.get(label, [])
        if not items:
            continue
        wrote_canon = True
        lines.append(f"**Category: {label.value}**")
        lines += [f"- {c.get('summary', '')}" for c in items]
        lines.append("")
    if not wrote_canon:
        lines += ["No approved canon yet.", ""]

    # 4. Planned Next Session — the GM's approved prep, explicitly NOT canon
    # (it isn't derived from approved session notes or world-building).
    if next_session_plan and next_session_plan.strip():
        lines += ["## Planned Next Session (not canon — an approved plan, not yet played)", ""]
        lines += [line for line in next_session_plan.strip().splitlines()]
        lines += [""]

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["build_world_export_markdown"]
