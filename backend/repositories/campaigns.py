"""Campaign persistence behind a stable API-facing repository contract."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

from backend.db import connect, postgres_enabled


class CampaignRepository(Protocol):
    storage_label: str

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]: ...
    def get(self, campaign_id: str) -> dict[str, Any] | None: ...
    def create(self, *, name: str, description: str, owner_id: str | None = None) -> dict[str, Any]: ...
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
        "visibility": row.get("visibility", "private"),
        "model": row.get("model_profile", row.get("model", "balanced")),
    }


class InMemoryCampaignRepository:
    """Adapter for the existing prototype store when DATABASE_URL is absent."""

    storage_label = "in_memory_development"

    def __init__(self, store: Any) -> None:
        self.store = store

    def _list_sections(self) -> list[dict[str, Any]]:
        return [
            {**section, "campaigns": [_api_campaign_memory(item) for item in section["campaigns"]]}
            for section in self.store.sections
        ]

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        from backend.accounts import accounts
        result = []
        seen = set()
        with self.store.lock:
            for section in self._list_sections():
                for campaign in section['campaigns']:
                    cid = campaign['campaignId']
                    if cid not in seen and accounts.role(cid, user_id):
                        seen.add(cid)
                        result.append(accounts.decorate(campaign, user_id))
        return result

    def get(self, campaign_id: str) -> dict[str, Any] | None:
        campaign = self.store.campaign(campaign_id)
        return _api_campaign_memory(campaign) if campaign else None

    def create(self, *, name: str, description: str, owner_id: str | None = None) -> dict[str, Any]:
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
    return dict(campaign)


class PostgresCampaignRepository:
    """Persist campaigns in PostgreSQL while preserving the frontend DTO."""

    storage_label = "postgresql"

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute("""
                SELECT c.*, a.role AS user_role,
                       owner.id AS owner_id, owner.name AS owner_name, owner.email AS owner_email,
                       COALESCE(roster.players, '[]'::jsonb) AS players
                FROM campaigns c
                JOIN campaign_access a ON a.campaign_id=c.id AND a.user_id=%s
                LEFT JOIN campaign_access ownership ON ownership.campaign_id=c.id AND ownership.role='owner'
                LEFT JOIN app_users owner ON owner.id=ownership.user_id
                LEFT JOIN LATERAL (
                    SELECT jsonb_agg(jsonb_build_object('id',u.id,'name',u.name) ORDER BY lower(u.name),u.id) AS players
                    FROM campaign_access p JOIN app_users u ON u.id=p.user_id
                    WHERE p.campaign_id=c.id AND p.role='player'
                ) roster ON true
                ORDER BY c.updated_at DESC,c.name
            """, (user_id,)).fetchall()
        return [{**_api_campaign(row), 'role':row['user_role'], 'players':row['players'],
                 'owner': {'id':row['owner_id'],'name':row['owner_name'],'email':row['owner_email']} if row['owner_id'] else None} for row in rows]

    def get(self, campaign_id: str) -> dict[str, Any] | None:
        with connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, description, status, role, last_session_number,
                       next_session_label, updated_at, world_status, visibility, model_profile
                FROM campaigns WHERE id = %s
                """,
                (campaign_id,),
            ).fetchone()
        return _api_campaign(row) if row else None

    def create(self, *, name: str, description: str, owner_id: str | None = None) -> dict[str, Any]:
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
                          next_session_label, updated_at, world_status, visibility, model_profile
                """,
                (campaign_id, name, description or "New campaign world awaiting its first session."),
            ).fetchone()
            if owner_id:
                connection.execute("INSERT INTO campaign_access(campaign_id,user_id,role) VALUES (%s,%s,'owner')", (campaign_id,owner_id))
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
                          next_session_label, updated_at, world_status, visibility, model_profile
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
                          next_session_label, updated_at, world_status, visibility, model_profile
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
