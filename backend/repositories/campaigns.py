"""Campaign persistence behind a stable API-facing repository contract."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

from backend.db import connect, postgres_enabled


class CampaignRepository(Protocol):
    storage_label: str

    def list_sections(self) -> list[dict[str, Any]]: ...
    def get(self, campaign_id: str) -> dict[str, Any] | None: ...
    def create(self, *, name: str, description: str) -> dict[str, Any]: ...
    def update(self, campaign_id: str, patch: Mapping[str, str]) -> dict[str, Any] | None: ...
    def seal_world(self, campaign_id: str) -> dict[str, Any] | None: ...
    def is_ready(self) -> bool: ...


def _timestamp(value: datetime | str) -> str:
    if isinstance(value, str):
        return value
    return value.isoformat().replace("+00:00", "Z")


def _api_campaign(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "campaignId": row["id"],
        "name": row["name"],
        "role": row.get("role", "owner"),
        "status": row["status"],
        "lastSessionNumber": row.get("last_session_number", 0),
        "nextSessionLabel": row.get("next_session_label", "Initial world setup incomplete"),
        "updatedAt": _timestamp(row["updated_at"]),
        "description": row["description"],
        "worldStatus": row.get("world_status", "draft"),
    }


class InMemoryCampaignRepository:
    """Adapter for the existing prototype store when DATABASE_URL is absent."""

    storage_label = "in_memory_development"

    def __init__(self, store: Any) -> None:
        self.store = store

    def list_sections(self) -> list[dict[str, Any]]:
        return [
            {**section, "campaigns": [_api_campaign_memory(item) for item in section["campaigns"]]}
            for section in self.store.sections
        ]

    def get(self, campaign_id: str) -> dict[str, Any] | None:
        campaign = self.store.campaign(campaign_id)
        return _api_campaign_memory(campaign) if campaign else None

    def create(self, *, name: str, description: str) -> dict[str, Any]:
        campaign = self.store._campaign(
            f"campaign_{uuid4().hex[:12]}", name, "owner", "planning", 0,
            "Initial world setup incomplete", description or "New campaign world awaiting its first session.",
        )
        next(section for section in self.store.sections if section["id"] == "owned")["campaigns"].insert(0, campaign)
        return _api_campaign_memory(campaign)

    def update(self, campaign_id: str, patch: Mapping[str, str]) -> dict[str, Any] | None:
        campaign = self.store.campaign(campaign_id)
        if not campaign:
            return None
        for key, value in patch.items():
            campaign[key] = value
        campaign["updatedAt"] = datetime.now().astimezone().isoformat().replace("+00:00", "Z")
        return _api_campaign_memory(campaign)

    def seal_world(self, campaign_id: str) -> dict[str, Any] | None:
        campaign = self.store.campaign(campaign_id)
        if not campaign:
            return None
        campaign["worldStatus"] = "sealed"
        return _api_campaign_memory(campaign)

    def is_ready(self) -> bool:
        return True


def _api_campaign_memory(campaign: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in campaign.items() if key not in {"visibility", "model"}}


class PostgresCampaignRepository:
    """Persist campaigns in PostgreSQL while preserving the frontend DTO."""

    storage_label = "postgresql"

    def list_sections(self) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, description, status, role, last_session_number,
                       next_session_label, updated_at, world_status
                FROM campaigns
                ORDER BY updated_at DESC, name
                """
            ).fetchall()
        return [
            {
                "id": "owned",
                "title": "Owned",
                "subtitle": "Campaign worlds where you control settings, canon, players, and AI memory.",
                "campaigns": [_api_campaign(row) for row in rows],
            },
            {"id": "shared", "title": "Shared", "subtitle": "Campaigns another GM invited you to view or contribute to.", "campaigns": []},
            {"id": "running", "title": "In progress", "subtitle": "Tables you are actively running or preparing.", "campaigns": []},
        ]

    def get(self, campaign_id: str) -> dict[str, Any] | None:
        with connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, description, status, role, last_session_number,
                       next_session_label, updated_at, world_status
                FROM campaigns WHERE id = %s
                """,
                (campaign_id,),
            ).fetchone()
        return _api_campaign(row) if row else None

    def create(self, *, name: str, description: str) -> dict[str, Any]:
        campaign_id = f"campaign_{uuid4().hex[:12]}"
        with connect() as connection:
            row = connection.execute(
                """
                INSERT INTO campaigns (
                    id, name, description, status, role, last_session_number,
                    next_session_label, visibility, model_profile
                ) VALUES (%s, %s, %s, 'planning', 'owner', 0,
                          'Initial world setup incomplete', 'private', 'balanced')
                RETURNING id, name, description, status, role, last_session_number,
                          next_session_label, updated_at, world_status
                """,
                (campaign_id, name, description or "New campaign world awaiting its first session."),
            ).fetchone()
        return _api_campaign(row)

    def update(self, campaign_id: str, patch: Mapping[str, str]) -> dict[str, Any] | None:
        columns = {"name": "name", "description": "description", "visibility": "visibility", "model": "model_profile"}
        assignments: list[str] = []
        values: list[str] = []
        for key, value in patch.items():
            column = columns[key]
            assignments.append(f"{column} = %s")
            values.append(value)
        if not assignments:
            return self.get(campaign_id)
        values.append(campaign_id)
        with connect() as connection:
            row = connection.execute(
                f"""
                UPDATE campaigns
                SET {', '.join(assignments)}, updated_at = now()
                WHERE id = %s
                RETURNING id, name, description, status, role, last_session_number,
                          next_session_label, updated_at, world_status
                """,
                values,
            ).fetchone()
        return _api_campaign(row) if row else None

    def seal_world(self, campaign_id: str) -> dict[str, Any] | None:
        with connect() as connection:
            row = connection.execute(
                """
                UPDATE campaigns SET world_status = 'sealed', updated_at = now()
                WHERE id = %s
                RETURNING id, name, description, status, role, last_session_number,
                          next_session_label, updated_at, world_status
                """,
                (campaign_id,),
            ).fetchone()
        return _api_campaign(row) if row else None

    def is_ready(self) -> bool:
        try:
            with connect(autocommit=True) as connection:
                connection.execute("SELECT 1")
            return True
        except Exception:
            return False


def build_campaign_repository(store: Any) -> CampaignRepository:
    return PostgresCampaignRepository() if postgres_enabled() else InMemoryCampaignRepository(store)
