"""Seed a demo-rich campaign into PostgreSQL from the synthetic dataset.

Loads `synthetic-data/ashes_kestrel_10_session_data_set.json` into the schema so a
fresh database opens on a fully built "Ashes of Kestrel Vale" world with 10 sessions
of real GM notes ready to run extraction against. It seeds:

    campaigns, world_entries, sessions, session_notes

It intentionally does NOT pre-create proposals or canon — the demo value is watching
the AI review loop turn the seeded raw notes into proposals you approve.

Idempotent: every row uses a deterministic id and `ON CONFLICT DO NOTHING`, so
re-running adds nothing. Requires DATABASE_URL (see backend/db.py).

Run from the repo root:
    DATABASE_URL=... backend/.venv/bin/python -m backend.seed_demo
"""

from __future__ import annotations

import json
from pathlib import Path

from psycopg.types.json import Jsonb

from backend.db import connect, postgres_enabled

DATASET = Path(__file__).resolve().parents[1] / "synthetic-data" / "ashes_kestrel_10_session_data_set.json"

_STATUS_MAP = {"active_after_10_sessions": "active"}


def _title_from_note(note: str, category: str) -> str:
    first = note.strip().split(". ")[0].strip()
    if 8 <= len(first) <= 90:
        return first.rstrip(".")
    return f"{category.replace('_', ' ').title()} entry"


def seed() -> dict[str, int]:
    data = json.loads(DATASET.read_text())
    campaign = data["campaign"]
    campaign_id = campaign["campaign_id"]
    counts = {"campaigns": 0, "world_entries": 0, "sessions": 0, "session_notes": 0}

    with connect() as connection, connection.transaction():
        counts["campaigns"] = connection.execute(
            """
            INSERT INTO campaigns (id, name, description, system, status, tone, logline,
                                   role, last_session_number, next_session_label, visibility, model_profile,
                                   world_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'owner', %s, %s, 'private', 'balanced', 'sealed')
            ON CONFLICT (id) DO NOTHING
            """,
            (
                campaign_id, campaign["name"], campaign.get("logline", ""), campaign.get("system"),
                _STATUS_MAP.get(campaign.get("status", ""), "active"), Jsonb(campaign.get("tone", [])),
                campaign.get("logline"), 10, "Run Session 11 this week",
            ),
        ).rowcount

        for category, block in data.get("world", {}).items():
            if not isinstance(block, dict):
                continue
            category_tags = block.get("category_tags", [])
            for entry in block.get("entries", []):
                note = entry.get("note", "")
                if not note:
                    continue
                entry_id = entry.get("entry_id") or f"{category}_{counts['world_entries']}"
                counts["world_entries"] += connection.execute(
                    """
                    INSERT INTO world_entries (id, campaign_id, category, title, note, summary, entry_tags)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        f"entry_{entry_id}", campaign_id, category,
                        entry.get("title") or _title_from_note(note, category),
                        note, entry.get("summary"), Jsonb(entry.get("entry_tags") or category_tags),
                    ),
                ).rowcount

        for session in data.get("sessions", []):
            session_id = session["session_id"]
            counts["sessions"] += connection.execute(
                """
                INSERT INTO sessions (id, campaign_id, session_number, title, played_at, status, summary, related_entry_ids)
                VALUES (%s, %s, %s, %s, %s, 'completed', %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    session_id, campaign_id, session["session_number"], session.get("title"),
                    session.get("played_at"), session.get("summary"), Jsonb(session.get("related_entry_ids", [])),
                ),
            ).rowcount
            raw_notes = session.get("raw_notes")
            if raw_notes:
                counts["session_notes"] += connection.execute(
                    """
                    INSERT INTO session_notes (id, session_id, content, source_type)
                    VALUES (%s, %s, %s, 'manual_notes')
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (f"note_{session_id}", session_id, raw_notes),
                ).rowcount

    return counts


def main() -> None:
    if not postgres_enabled():
        raise SystemExit("DATABASE_URL is not configured — nothing to seed.")
    counts = seed()
    print("Seeded demo campaign 'Ashes of Kestrel Vale':")
    for table, n in counts.items():
        print(f"  {table}: +{n}")


if __name__ == "__main__":
    main()
