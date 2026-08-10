"""HTTP request models for the public /v1 API.

These models deliberately use the frontend's camelCase field names. Internal
campaign and AI domain models live in ``backend.schemas`` and use snake_case,
keeping the HTTP contract separate from persistence and worker contracts.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)


class CampaignPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    visibility: Literal["private", "shared"] | None = None
    model: Literal["cheap", "balanced", "premium"] | None = None


class WorldCategory(str, Enum):
    economy = "economy"
    politics = "politics"
    magic_systems = "magic_systems"
    world_artifacts = "world_artifacts"
    npcs = "npcs"
    government_organizations = "government_organizations"
    non_government_organizations = "non_government_organizations"
    laws = "laws"
    inhabitants = "inhabitants"
    ecosystems = "ecosystems"
    cataclysmic_events = "cataclysmic_events"
    general_overview = "general_overview"
    races = "races"
    jobs_and_roles = "jobs_and_roles"
    technology_systems = "technology_systems"
    regions = "regions"
    era = "era"
    player_characters = "player_characters"


class EntryCreate(BaseModel):
    category: WorldCategory
    title: str = Field(min_length=1, max_length=300)
    note: str = Field(min_length=1, max_length=50_000)
    tags: list[str] = Field(default_factory=list)


class NotesCreate(BaseModel):
    content: str = Field(min_length=1, max_length=50_000)
    sessionNumber: str = Field(min_length=1, max_length=12)
    title: str = Field(default="", max_length=300)
    startExtraction: bool = True


class PrepJobCreate(BaseModel):
    goal: str = Field(default="", max_length=2_000)
    tone: str = Field(default="balanced", max_length=100)
    memories: str = Field(default="", max_length=5_000)


class SessionPrepApprove(BaseModel):
    """Approve a generated prep as the GM's plan for next session. NOT canon —
    canon only ever comes from approved session notes or world-building; this
    just marks a prep draft as ready and captures the GM's final (possibly
    edited) text so it can be included in the world export."""

    prepId: str = Field(min_length=1)
    outline: str = Field(min_length=1, max_length=20_000)


class WorldBuildCreate(BaseModel):
    """Build the campaign's world once, then seal it.

    The GM's saved entries are read server-side and extracted; `generateCategories`
    are the empty categories (snake_case WorldCategoryId) the GM checked for the AI
    to draft from scratch. Both paths produce only PENDING proposals for the review
    queue — nothing becomes canon without a GM decision. May be empty when the GM
    is building purely from their own entries.
    """

    generateCategories: list[WorldCategory] = Field(default_factory=list, max_length=18)


class ProposalReview(BaseModel):
    action: Literal["approve", "edit_approve", "reject"]
    editedPayload: dict[str, str] | None = None
    reason: str | None = Field(default=None, max_length=2_000)
