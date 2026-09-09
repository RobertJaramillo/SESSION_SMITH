import { useState } from "react";
import { PageHeader } from "../../components/Layout";
import type { CampaignSummary } from "../../domain/worldbuilding";

export function NotesPage({
  campaign,
  extracting,
  onSubmit,
}: {
  campaign: CampaignSummary;
  extracting: boolean;
  onSubmit: (submission: {
    note: string;
    sessionNumber: string;
    title: string;
  }) => void;
}) {
  const nextSession = campaign.lastSessionNumber + 1;
  const [sessionNumber, setSessionNumber] = useState(`${nextSession}`);
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const canSubmit =
    note.trim().length > 0 && sessionNumber.trim().length > 0 && !extracting;

  return (
    <section>
      <PageHeader
        kicker="Session Notes"
        title="Log each session as its own entry"
        body="Session 0 is your initial world setup; Session 1 and up capture later play. Paste your raw notes and the AI worker turns them into canon candidates for your review."
      />
      <article className="card full-card">
        <label>
          Session number
          <input
            min="0"
            onChange={(event) => setSessionNumber(event.target.value)}
            type="number"
            value={sessionNumber}
          />
        </label>
        <label>
          Session title
          <input
            onChange={(event) => setTitle(event.target.value)}
            placeholder={`Session ${nextSession} — short title`}
            value={title}
          />
        </label>
        <label>
          Raw table notes
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Paste this session's raw table notes. When you submit, the AI worker reads them and proposes canon changes for your review."
          />
        </label>
        <div className="button-row">
          <button
            disabled={!canSubmit}
            onClick={() => onSubmit({ note, sessionNumber, title })}
            type="button"
          >
            {extracting
              ? "Extracting canon candidates…"
              : "Submit notes for AI review"}
          </button>
          <button
            className="secondary"
            disabled={extracting}
            onClick={() => {
              setNote("");
              setTitle("");
            }}
            type="button"
          >
            Clear
          </button>
        </div>
        {extracting && (
          <p className="empty-state" role="status">
            The AI worker is reading your notes and drafting proposed canon
            changes…
          </p>
        )}
      </article>
    </section>
  );
}
