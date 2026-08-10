"""
evaluation/dataset.py — Load session notes from the sample dataset.

The evaluation only needs the raw session notes (the input both systems consume).
This adapts the shape in ashes_kestrel_10_session_data_set.json into the tiny
SessionInput list the generators expect. Keeping the adapter here means the rest
of the pipeline is agnostic to the on-disk JSON layout.
"""

from __future__ import annotations

import json
from pathlib import Path

from .generators import SessionInput

# Default location of the bundled sample dataset.
DEFAULT_DATASET = (
    Path(__file__).resolve().parents[2] / "synthetic-data" / "ashes_kestrel_10_session_data_set.json"
)


def load_sessions(dataset_path: str | Path | None = None) -> tuple[str, list[SessionInput]]:
    """Return (campaign_id, sessions) from the dataset JSON.

    Sessions are returned in play order (by session_number) so the sequential
    baseline sees them in the same order a GM would.
    """
    path = Path(dataset_path) if dataset_path else DEFAULT_DATASET
    data = json.loads(path.read_text())

    campaign_id = data.get("campaign", {}).get("campaign_id", "unknown_campaign")

    raw_sessions = sorted(
        data.get("sessions", []),
        key=lambda s: s.get("session_number", 0),
    )
    sessions = [
        SessionInput(
            session_id=s["session_id"],
            title=s.get("title", s["session_id"]),
            # Prefer raw_notes (the untrusted GM input); fall back to summary.
            raw_notes=s.get("raw_notes") or s.get("summary", ""),
        )
        for s in raw_sessions
    ]
    return campaign_id, sessions


__all__ = ["load_sessions", "DEFAULT_DATASET"]
