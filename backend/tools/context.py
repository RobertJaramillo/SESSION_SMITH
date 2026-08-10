"""
context.py — Context loading tools.

Loads the campaign shell + world framework that frame every prompt.
(AI_ARCHITECTURE.md §12.1)
"""

from __future__ import annotations

from backend.schemas import Campaign, WorldFramework
from backend.store import get_store


def load_campaign_context(campaign_id: str) -> tuple[Campaign, WorldFramework | None]:
    """Load the campaign shell + world framework (tone, themes, constraints).
    These frame every prompt. (AI_ARCHITECTURE.md §12.1: load_campaign_context)"""
    corpus = get_store().get_corpus(campaign_id)
    if corpus.campaign is None:
        raise ValueError(f"unknown campaign_id: {campaign_id}")
    return corpus.campaign, corpus.world_framework


__all__ = ["load_campaign_context"]
