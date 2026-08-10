"""Development HTTP API for the Campaign Orchestration frontend.

Run from the repository root:
    backend/.venv/bin/uvicorn backend.app:app --reload --port 8000

The endpoint shapes match ``frontend/src/api/client.ts``. Campaign CRUD uses
PostgreSQL whenever ``DATABASE_URL`` is configured; the in-memory prototype
remains the fallback for UI-only work. The trust boundary is already enforced
here: only a GM review action writes canon, and raw notes are never returned as
canon.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
import backend.worker as worker
from backend.db import postgres_enabled
from backend.llm_provider import get_provider
from backend.models.requests import CampaignCreate, CampaignPatch, EntryCreate, NotesCreate, PrepJobCreate, ProposalReview, SessionPrepApprove, WorldBuildCreate
from backend.repositories.campaigns import build_campaign_repository
from backend.repositories.entries import PostgresEntryRepository
from backend.repositories.jobs import PostgresJobRepository
from backend.repositories.proposals import PostgresProposalRepository
from backend.exporting import build_world_export_markdown
from backend.repositories.sessions import PostgresSessionRepository
from backend.schemas import AIJob, JobType, SessionPrepOutput, WorldCategoryLabel, classify_canon_origin


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": f"{resource}_not_found", "message": f"{resource.replace('_', ' ').title()} not found."},
    )


class CampaignStore:
    """Thread-safe development state for non-persistent workspace resources."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.sections: list[dict[str, Any]] = [
            {
                "id": "owned",
                "title": "Owned",
                "subtitle": "Campaign worlds where you control settings, canon, players, and AI memory.",
                "campaigns": [
                    self._campaign(
                        "campaign_ashes_of_kestrel_vale", "Ashes of Kestrel Vale", "owner", "active", 10,
                        "Session 11 prep needed", "Dark political fantasy about oath law, buried history, and the Flood of Bells.",
                        world_status="sealed",
                    ),
                    self._campaign(
                        "campaign_glass_moon_exile", "Glass Moon Exile", "owner", "planning", 0,
                        "Initial world setup incomplete", "Planar survival campaign draft waiting for session 0 worldbuilding notes.",
                    ),
                ],
            },
            {
                "id": "shared",
                "title": "Shared",
                "subtitle": "Campaigns another GM invited you to view or contribute to as a player or collaborator.",
                "campaigns": [self._campaign(
                    "campaign_cinder_archive", "The Cinder Archive", "player", "active", 4,
                    "Awaiting GM notes", "Library-city mystery shared with you as a player character contributor.",
                    world_status="sealed",
                )],
            },
            {
                "id": "running",
                "title": "In progress",
                "subtitle": "Tables you are actively running or preparing right now.",
                "campaigns": [self._campaign(
                    "campaign_ashes_of_kestrel_vale", "Ashes of Kestrel Vale", "gm", "active", 10,
                    "Run Session 11 this week", "Current live table with pending review proposals from sessions 9 and 10.",
                    world_status="sealed",
                )],
            },
        ]
        self.states: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _campaign(
        campaign_id: str, name: str, role: str, campaign_status: str, last_session_number: int,
        next_session_label: str, description: str, world_status: str = "draft",
    ) -> dict[str, Any]:
        return {
            "campaignId": campaign_id, "name": name, "role": role, "status": campaign_status,
            "lastSessionNumber": last_session_number, "nextSessionLabel": next_session_label,
            "updatedAt": "2026-07-25T00:00:00Z", "description": description,
            "worldStatus": world_status,
            "visibility": "private", "model": "balanced",
        }

    def campaign(self, campaign_id: str) -> dict[str, Any] | None:
        for section in self.sections:
            for campaign in section["campaigns"]:
                if campaign["campaignId"] == campaign_id:
                    return campaign
        return None

    def ensure_state(self, campaign_id: str, *, campaign_exists: bool = True) -> dict[str, Any]:
        if not campaign_exists:
            raise _not_found("campaign")
        if campaign_id not in self.states:
            canon_seed = [
                ("Government Organizations", "The Iron Court sets and enforces river-crossing tariffs."),
                ("Magic Systems", "Binding oaths require a witnessed vow to hold power."),
                ("Regions", "Kestrel Vale sits downriver of the drowned bell tower."),
            ] if campaign_id == "campaign_ashes_of_kestrel_vale" else []
            self.states[campaign_id] = {
                "entries": [], "proposals": [],
                "canon": [{"id": _id("canon"), "category": category, "summary": summary} for category, summary in canon_seed],
                "sessionDocCount": 11 if campaign_id == "campaign_ashes_of_kestrel_vale" else 0,
                "recentActivity": [],
                "prep": None,  # {"prepId", "title", "outline", "status"} once generated
            }
        return self.states[campaign_id]


store = CampaignStore()
campaigns = build_campaign_repository(store)
entries = PostgresEntryRepository()
sessions = PostgresSessionRepository()
jobs = PostgresJobRepository()
proposals = PostgresProposalRepository()
def _configure_llm_provider():
    """Read LLM_PROVIDER/OPENAI_API_KEY from the environment (set by ./run and
    compose.yaml). Falls back to the offline demo provider when unset."""
    provider_name = os.getenv("LLM_PROVIDER", "demo")
    if provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("LLM_PROVIDER=openai requires OPENAI_API_KEY to be set.")
        return get_provider("openai", api_key=api_key)
    return get_provider(provider_name)


_llm_provider = _configure_llm_provider()
app = FastAPI(title="AI Campaign Orchestration API", version="0.1.0-dev")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> Any:
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "request_error", "message": str(exc.detail)}
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


def data(value: Any, response_status: int = status.HTTP_200_OK) -> Any:
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=response_status, content={"data": value})


def _campaign_or_404(campaign_id: str) -> dict[str, Any]:
    campaign = campaigns.get(campaign_id)
    if not campaign:
        raise _not_found("campaign")
    return campaign


@app.get("/v1/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/readyz")
def readyz() -> dict[str, str]:
    if not campaigns.is_ready():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "database_unavailable", "message": "Database is unavailable."})
    return {"status": "ready", "storage": campaigns.storage_label}


@app.get("/v1/campaigns")
def list_campaigns() -> Any:
    with store.lock:
        return data(campaigns.list_sections())


@app.post("/v1/campaigns")
def create_campaign(payload: CampaignCreate) -> Any:
    with store.lock:
        campaign = campaigns.create(name=payload.name.strip(), description=payload.description.strip())
    return data(campaign, status.HTTP_201_CREATED)


@app.get("/v1/campaigns/{campaign_id}")
def get_campaign(campaign_id: str) -> Any:
    with store.lock:
        return data(_campaign_or_404(campaign_id))


@app.patch("/v1/campaigns/{campaign_id}")
def patch_campaign(campaign_id: str, payload: CampaignPatch) -> Any:
    with store.lock:
        patch = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in payload.model_dump(exclude_none=True).items()
        }
        campaign = campaigns.update(campaign_id, patch)
        if not campaign:
            raise _not_found("campaign")
        return data(campaign)


@app.get("/v1/campaigns/{campaign_id}/workspace")
def workspace(campaign_id: str) -> Any:
    with store.lock:
        _campaign_or_404(campaign_id)
        if postgres_enabled():
            return data({
                "sessionDocCount": sessions.count(campaign_id),
                "canonMemoryCount": proposals.canon_count(campaign_id),
                "proposalsWaiting": proposals.pending_count(campaign_id),
                "recentActivity": sessions.recent_activity(campaign_id),
            })
        state = store.ensure_state(campaign_id)
        return data({
            "sessionDocCount": state["sessionDocCount"], "canonMemoryCount": len(state["canon"]),
            "proposalsWaiting": sum(item["status"] == "pending" for item in state["proposals"]),
            "recentActivity": state["recentActivity"],
        })


@app.get("/v1/campaigns/{campaign_id}/entries")
def list_entries(campaign_id: str) -> Any:
    with store.lock:
        _campaign_or_404(campaign_id)
        if postgres_enabled():
            return data(entries.list(campaign_id))
        return data(store.ensure_state(campaign_id)["entries"])


@app.post("/v1/campaigns/{campaign_id}/entries")
def create_entry(campaign_id: str, payload: EntryCreate) -> Any:
    with store.lock:
        campaign = _campaign_or_404(campaign_id)
        if campaign.get("worldStatus") == "sealed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "world_sealed", "message": "This world is sealed. Add new details through session notes."},
            )
        if postgres_enabled():
            return data(
                entries.create(
                    campaign_id,
                    category=payload.category.value,
                    title=payload.title.strip(),
                    note=payload.note.strip(),
                    tags=payload.tags,
                ),
                status.HTTP_201_CREATED,
            )
        state = store.ensure_state(campaign_id)
        entry = {
            "id": _id("entry"),
            "category": payload.category.value,
            "title": payload.title.strip(),
            "note": payload.note.strip(),
            "tags": [tag.strip() for tag in payload.tags if tag.strip()],
        }
        state["entries"].insert(0, entry)
        return data(entry, status.HTTP_201_CREATED)


def _inmemory_canon_with_origin(state: dict[str, Any]) -> list[dict[str, Any]]:
    """In-memory canon rows carry `promptVersion` (see review_proposal); derive
    `origin` from it at read time, mirroring proposals.list_canon()'s Postgres
    shape so callers don't need to branch on backend."""
    return [{**row, "origin": classify_canon_origin(row.get("promptVersion"))} for row in state["canon"]]


@app.get("/v1/campaigns/{campaign_id}/canon-events")
def list_canon_events(campaign_id: str) -> Any:
    with store.lock:
        _campaign_or_404(campaign_id)
        if postgres_enabled():
            return data(proposals.list_canon(campaign_id))
        return data(_inmemory_canon_with_origin(store.ensure_state(campaign_id)))


@app.get("/v1/campaigns/{campaign_id}/world-export")
def world_export(
    campaign_id: str,
    fmt: str = Query("pdf", alias="format"),
    scope: str = Query("all", pattern="^(all|session_notes)$"),
) -> Response:
    """Export the world (overview + GM entries + approved canon) as a document
    for evaluation. `format=pdf` (default) or `md`. `scope=all` (default) includes
    every approved canon entry, as a GM would want; `scope=session_notes` limits
    canon to session-note-derived entries only, excluding deliberately-creative
    World Builder canon (see AI_ARCHITECTURE.md §6) — use this scope when feeding
    the export to the evaluation pipeline's faithfulness-to-notes scoring, since
    World Builder output isn't trying to be faithful to session notes by design.
    Pure read of stored data — no AI call, so it is $0 and repeatable."""
    with store.lock:
        campaign = _campaign_or_404(campaign_id)
        if postgres_enabled():
            entry_rows = entries.list(campaign_id)
            canon_rows = proposals.list_canon(campaign_id)
            approved_prep = jobs.get_latest_approved_prep(campaign_id)
        else:
            state = store.ensure_state(campaign_id)
            entry_rows = state["entries"]
            canon_rows = _inmemory_canon_with_origin(state)
            prep_state = state.get("prep")
            approved_prep = prep_state if prep_state and prep_state.get("status") == "approved" else None

    next_session_plan = approved_prep.get("approved_outline") if approved_prep else None
    origin_filter = "session_notes" if scope == "session_notes" else None
    markdown = build_world_export_markdown(
        campaign["name"], entry_rows, canon_rows, next_session_plan=next_session_plan, origin_filter=origin_filter,
    )

    if fmt == "md":
        return Response(
            content=markdown,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{campaign_id}-world.md"'},
        )

    try:
        from backend.pdf_render import render_markdown_to_pdf_bytes
    except Exception as error:  # reportlab missing / broken
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "pdf_unavailable", "message": f"PDF rendering is unavailable: {error}. Use ?format=md."},
        ) from error

    title = f"{campaign['name']} — World Export"
    pdf_bytes = render_markdown_to_pdf_bytes(markdown, title=title, footer=title)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{campaign_id}-world.pdf"'},
    )


@app.get("/v1/campaigns/{campaign_id}/memory-proposals")
def list_proposals(campaign_id: str, proposal_status: str | None = None, status: str | None = None) -> Any:
    with store.lock:
        _campaign_or_404(campaign_id)
        if postgres_enabled():
            return data(proposals.list(campaign_id, proposal_status or status))
        pending_proposals = store.ensure_state(campaign_id)["proposals"]
        selected_status = proposal_status or status
        return data([proposal for proposal in pending_proposals if not selected_status or proposal["status"] == selected_status])


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


def _complete_extraction(job_id: str, campaign_id: str, payload: NotesCreate, note_id: str | None = None, session_id: str | None = None) -> None:
    source = f"Session {payload.sessionNumber}" + (f" — {payload.title.strip()}" if payload.title.strip() else "")
    if postgres_enabled():
        job = AIJob(id=job_id, campaign_id=campaign_id, session_id=session_id, job_type=JobType.extract_memory)
        try:
            created = worker.extract_memory(job, note_id or "", payload.content, _llm_provider)
        except Exception as error:
            jobs.fail(job_id, str(error))
            return
        jobs.complete(job_id, {"proposalIds": [proposal.id for proposal in created]})
        return
    with store.lock:
        job = store.jobs[job_id]
        proposals = _proposal_from_notes(payload.content, source)
        state = store.ensure_state(campaign_id)
        state["proposals"] = proposals + state["proposals"]
        state["sessionDocCount"] += 1
        state["recentActivity"].insert(0, {"actor": source, "detail": "Raw notes submitted for GM review."})
        job.update({"status": "succeeded", "progress": 100, "result": {"proposalIds": [item["id"] for item in proposals]}})


@app.post("/v1/campaigns/{campaign_id}/notes")
def submit_notes(campaign_id: str, payload: NotesCreate, background_tasks: BackgroundTasks) -> Any:
    with store.lock:
        _campaign_or_404(campaign_id)
        if postgres_enabled():
            try:
                note_id, session_id = sessions.create_note(
                    campaign_id, content=payload.content, session_number=payload.sessionNumber, title=payload.title,
                )
            except ValueError as error:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "invalid_session_number", "message": str(error)}) from error
            job_id = jobs.create(campaign_id, job_type="extract_memory", session_id=session_id)
            if payload.startExtraction:
                background_tasks.add_task(_complete_extraction, job_id, campaign_id, payload, note_id, session_id)
            return data({"noteId": note_id, "jobId": job_id, "status": "pending"}, status.HTTP_202_ACCEPTED)
        store.ensure_state(campaign_id)
        note_id, job_id = _id("note"), _id("job")
        try:
            session_number = int(payload.sessionNumber)
        except ValueError:
            session_number = None
        store.jobs[job_id] = {
            "id": job_id, "type": "extract_canon", "status": "pending", "progress": 0, "result": None,
            "error": None, "campaignId": campaign_id, "sessionNumber": session_number,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
    if payload.startExtraction:
        background_tasks.add_task(_complete_extraction, job_id, campaign_id, payload)
    return data({"noteId": note_id, "jobId": job_id, "status": "pending"}, status.HTTP_202_ACCEPTED)


def _outline_from_prep(sections: SessionPrepOutput) -> list[str]:
    """Flatten the structured prep output into the flat list the frontend's
    prep textarea seeds from (App.tsx reads job.result.outline). The full
    structured output is never lost — it's stored as-is in session_preps.sections."""
    lines: list[str] = []
    if sections.opening_scene:
        lines.append(f"Opening: {sections.opening_scene}")
    lines.extend(f"{beat.title}: {beat.description}" for beat in sections.main_beats)
    lines.extend(f"Open question: {question}" for question in sections.open_questions_for_gm)
    return lines or [sections.summary]


def _complete_prep(job_id: str, campaign_id: str, payload: PrepJobCreate) -> None:
    if postgres_enabled():
        job = AIJob(id=job_id, campaign_id=campaign_id, job_type=JobType.generate_session_prep)
        focus = payload.goal.strip() or None
        if focus and payload.tone.strip():
            focus = f"{focus} (tone: {payload.tone.strip()})"
        manual_memories = payload.memories.strip() or None
        try:
            prep = worker.generate_session_prep(job, focus, _llm_provider, manual_memories=manual_memories)
        except Exception as error:
            jobs.fail(job_id, str(error))
            return
        jobs.complete(job_id, {"outline": _outline_from_prep(prep.sections), "prepId": prep.id})
        return
    outline = [
        f"Opening scene aligned to: {payload.goal.strip() or 'the current campaign situation'}.",
        f"Escalate the session with a {payload.tone.strip() or 'balanced'} complication.",
        "Present two clues that build on approved canon.",
        "End with a player-driven choice and a clear next hook.",
    ]
    prep_id = _id("prep")
    with store.lock:
        state = store.ensure_state(campaign_id)
        state["prep"] = {"prepId": prep_id, "outline": "\n".join(outline), "status": "draft"}
        store.jobs[job_id].update({"status": "succeeded", "progress": 100, "result": {"outline": outline, "prepId": prep_id}})


@app.post("/v1/campaigns/{campaign_id}/prep-jobs")
def submit_prep_job(campaign_id: str, payload: PrepJobCreate, background_tasks: BackgroundTasks) -> Any:
    with store.lock:
        _campaign_or_404(campaign_id)
        if postgres_enabled():
            job_id = jobs.create(campaign_id, job_type="generate_session_prep")
            background_tasks.add_task(_complete_prep, job_id, campaign_id, payload)
            return data({"jobId": job_id, "status": "pending"}, status.HTTP_202_ACCEPTED)
        store.ensure_state(campaign_id)
        job_id = _id("job")
        store.jobs[job_id] = {
            "id": job_id, "type": "generate_prep", "status": "pending", "progress": 0, "result": None,
            "error": None, "campaignId": campaign_id, "sessionNumber": None,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
    background_tasks.add_task(_complete_prep, job_id, campaign_id, payload)
    return data({"jobId": job_id, "status": "pending"}, status.HTTP_202_ACCEPTED)


@app.get("/v1/campaigns/{campaign_id}/session-prep")
def get_session_prep(campaign_id: str) -> Any:
    """The latest generated prep (draft or approved), for restoring the Session
    Prep page — e.g. after a reload. Null if nothing's been generated yet."""
    with store.lock:
        _campaign_or_404(campaign_id)
        if postgres_enabled():
            row = jobs.get_latest_prep(campaign_id)
            if not row:
                return data(None)
            outline = row["approved_outline"] or "\n".join(_outline_from_prep(SessionPrepOutput(**row["sections"])))
            return data({"prepId": row["id"], "outline": outline, "status": row["status"]})
        state = store.ensure_state(campaign_id)
        return data(state.get("prep"))


@app.post("/v1/campaigns/{campaign_id}/session-prep/approve")
def approve_session_prep(campaign_id: str, payload: SessionPrepApprove) -> Any:
    """Approve a prep as the GM's plan for next session, storing their final
    (possibly edited) text. NOT canon — canon only comes from approved session
    notes or approved world-building; this is included in the world export as
    a separate, explicitly non-canon section."""
    with store.lock:
        _campaign_or_404(campaign_id)
        if postgres_enabled():
            row = jobs.approve_prep(payload.prepId, campaign_id, payload.outline.strip())
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "prep_not_found", "message": "Prep not found for this campaign."})
            return data({"prepId": row["id"], "outline": row["approved_outline"], "status": row["status"]})
        state = store.ensure_state(campaign_id)
        prep = state.get("prep")
        if not prep or prep["prepId"] != payload.prepId:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "prep_not_found", "message": "Prep not found for this campaign."})
        prep["outline"] = payload.outline.strip()
        prep["status"] = "approved"
        return data(prep)


def _entries_to_note(saved_entries: list[dict[str, Any]]) -> str:
    """Flatten saved World Builder entries into the labeled session-0 note the
    extraction workflow consumes ("[Category Label] Title\\nnote\\nTags: ..."), so
    the initial build reuses extract_memory rather than a bespoke path. Matches the
    frontend's buildWorldSubmissionContent shape."""
    blocks: list[str] = []
    for entry in saved_entries:
        cat = entry.get("category", "")
        label = WorldCategoryLabel[cat].value if cat in WorldCategoryLabel.__members__ else cat
        block = f"[{label}] {entry.get('title', '')}\n{entry.get('note', '')}"
        tags = entry.get("tags") or []
        if tags:
            block += f"\nTags: {', '.join(tags)}"
        blocks.append(block)
    return "\n\n".join(blocks)


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


def _complete_build_world(job_id: str, campaign_id: str, expand_labels: list[str], entries_note: str, campaign_name: str) -> None:
    """The world build: two-pass (bible -> grounded expansion) into PENDING
    proposals. Does NOT seal — sealing is a separate GM action after review.
    Regenerate-safe: prior pending proposals are cleared first so rebuilds replace
    the draft instead of piling up."""
    total = len(expand_labels)
    if postgres_enabled():
        try:
            proposals.reject_all_pending(campaign_id)  # regenerate: replace prior draft
            job = AIJob(id=job_id, campaign_id=campaign_id, job_type=JobType.extract_memory)

            def on_progress(completed: list[str], _total: int) -> None:
                jobs.update_progress(job_id, {"categoriesCompleted": completed, "totalCategories": total})

            created = worker.build_world(job, entries_note, expand_labels, _llm_provider, on_progress=on_progress)
        except Exception as error:
            jobs.fail(job_id, str(error))
            return
        categories_completed = sorted({p.category.value for p in created})
        jobs.complete(job_id, {
            "proposalIds": [p.id for p in created],
            "categoriesCompleted": categories_completed,
            "totalCategories": total,
        })
        return
    with store.lock:
        job = store.jobs[job_id]
        state = store.ensure_state(campaign_id)
        state["proposals"] = [p for p in state["proposals"] if p.get("status") != "pending"]  # regenerate
        new_proposals = _inmemory_build_proposals(campaign_name, entries_note, expand_labels)
        state["proposals"] = new_proposals + state["proposals"]
        state["recentActivity"].insert(0, {"actor": "AI Worker", "detail": f"Built the world — {len(new_proposals)} proposals for review."})
        categories_completed = sorted({item["category"] for item in new_proposals})
        job.update({
            "status": "succeeded", "progress": 100,
            "result": {
                "proposalIds": [item["id"] for item in new_proposals],
                "categoriesCompleted": categories_completed,
                "totalCategories": total,
            },
        })


@app.post("/v1/campaigns/{campaign_id}/build-world")
def build_world(campaign_id: str, payload: WorldBuildCreate, background_tasks: BackgroundTasks) -> Any:
    """Build (or rebuild) the world from the GM's entries + checked empty categories
    via the two-pass generator. Returns PENDING proposals for review; does NOT seal
    (that's the separate seal-world action). Repeatable while the world is draft."""
    with store.lock:
        campaign = _campaign_or_404(campaign_id)
        if campaign.get("worldStatus") == "sealed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "world_already_sealed", "message": "This world is sealed. Update it through session notes."},
            )
        saved_entries = entries.list(campaign_id) if postgres_enabled() else store.ensure_state(campaign_id)["entries"]
        entries_note = _entries_to_note(saved_entries)
        # Stage 2 expands EVERY world category, not just ones with entries or a
        # checked gap-fill box — the GM's own entries ground/steer the categories
        # they cover, and the AI fills in the rest, so every build covers all 18.
        expand_labels = [label.value for label in WorldCategoryLabel]

        if postgres_enabled():
            job_id = jobs.create(campaign_id, job_type="extract_memory")
        else:
            job_id = _id("job")
            store.jobs[job_id] = {
                "id": job_id, "type": "extract_memory", "status": "pending", "progress": 0, "result": None,
                "error": None, "campaignId": campaign_id, "sessionNumber": 0,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }
    background_tasks.add_task(_complete_build_world, job_id, campaign_id, expand_labels, entries_note, campaign["name"])
    return data({"jobId": job_id, "status": "pending"}, status.HTTP_202_ACCEPTED)


@app.post("/v1/campaigns/{campaign_id}/seal-world")
def seal_world(campaign_id: str) -> Any:
    """Explicitly seal the world after the GM has reviewed the build. The World
    Builder becomes read-only; all further change flows through session notes."""
    with store.lock:
        campaign = _campaign_or_404(campaign_id)
        if campaign.get("worldStatus") == "sealed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "world_already_sealed", "message": "This world is already sealed."},
            )
        sealed = campaigns.seal_world(campaign_id)
    return data(sealed)


@app.get("/v1/campaigns/{campaign_id}/jobs")
def list_jobs(campaign_id: str, job_type: str | None = None) -> Any:
    """Submission history for a campaign (newest first), including the real
    failure message so the UI never has to fall back to a generic 'it broke'."""
    with store.lock:
        _campaign_or_404(campaign_id)
        if postgres_enabled():
            return data(jobs.list(campaign_id, job_type=job_type))
        matches = [job for job in store.jobs.values() if job.get("campaignId") == campaign_id]
        if job_type:
            matches = [job for job in matches if job["type"] == job_type]
        matches.sort(key=lambda job: job.get("createdAt") or "", reverse=True)
        return data(matches)


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str) -> Any:
    with store.lock:
        if postgres_enabled():
            job = jobs.get(job_id)
            if not job:
                raise _not_found("job")
            return data(job)
        job = store.jobs.get(job_id)
        if not job:
            raise _not_found("job")
        return data(job)


@app.patch("/v1/memory-proposals/{proposal_id}")
def review_proposal(proposal_id: str, payload: ProposalReview) -> Any:
    if postgres_enabled():
        try:
            result = proposals.review(
                proposal_id,
                action=payload.action,
                edited_summary=(payload.editedPayload or {}).get("summary", "").strip() or None,
                reason=payload.reason,
            )
        except ValueError as error:
            code = str(error)
            response_status = status.HTTP_409_CONFLICT if code == "proposal_already_reviewed" else status.HTTP_422_UNPROCESSABLE_ENTITY
            message = "This proposal has already been reviewed." if code == "proposal_already_reviewed" else "An edited summary is required."
            raise HTTPException(status_code=response_status, detail={"code": code, "message": message}) from error
        if not result:
            raise _not_found("proposal")
        return data(result)
    with store.lock:
        for state in store.states.values():
            proposal = next((item for item in state["proposals"] if item["id"] == proposal_id), None)
            if not proposal:
                continue
            if proposal["status"] != "pending":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "proposal_already_reviewed", "message": "This proposal has already been reviewed."})
            created_canon_id: str | None = None
            if payload.action in {"approve", "edit_approve"}:
                if payload.action == "edit_approve":
                    edited_summary = (payload.editedPayload or {}).get("summary", "").strip()
                    if not edited_summary:
                        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "missing_edited_summary", "message": "An edited summary is required."})
                    proposal["summary"] = edited_summary
                proposal["status"] = "edited_approved" if payload.action == "edit_approve" else "approved"
                created_canon_id = _id("canon")
                state["canon"].append({
                    "id": created_canon_id, "category": proposal["category"], "summary": proposal["summary"],
                    "promptVersion": proposal.get("promptVersion"),
                })
            else:
                proposal["status"] = "rejected"
            return data({"proposalId": proposal_id, "status": proposal["status"], "createdCanonId": created_canon_id})
    raise _not_found("proposal")
