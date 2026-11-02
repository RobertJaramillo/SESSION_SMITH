import { useState } from "react";
import { PageHeader } from "../../components/Layout";
import type { ApiProposal, ReviewAction } from "../../api/types";

type OnReview = (id: string, action: ReviewAction, detail?: string) => void;

export function ReviewQueuePage({
  proposals,
  feedback,
  loading,
  error,
  onReview,
}: {
  proposals: ApiProposal[];
  feedback: string;
  loading: boolean;
  error: string;
  onReview: OnReview;
}) {
  return (
    <section>
      <PageHeader
        kicker="GM Review Queue"
        title="Approve, edit, or reject proposed memory"
        body="Nothing the AI proposes becomes canon until you approve it. Review each suggestion, then approve, edit, or reject it."
      />
      {feedback && (
        <p className="empty-state" role="status">
          {feedback}
        </p>
      )}
      {error && (
        <p className="settings-validation-message" role="status">
          {error}
        </p>
      )}
      {loading ? (
        <article className="card full-card">
          <p className="empty-state" role="status">
            Loading proposals…
          </p>
        </article>
      ) : proposals.length === 0 ? (
        <article className="card full-card">
          <p className="empty-state">
            No proposals waiting. Submit session notes and the AI will suggest
            canon changes here for your review.
          </p>
        </article>
      ) : (
        <div className="proposal-list">
          {proposals.map((proposal) => (
            <ProposalCard
              key={proposal.id}
              proposal={proposal}
              onReview={onReview}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export function ProposalCard({
  proposal,
  onReview,
}: {
  proposal: ApiProposal;
  onReview: OnReview;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "reject">("view");
  const [draft, setDraft] = useState(proposal.summary);
  const [reason, setReason] = useState("");
  return (
    <article className="card proposal-card">
      <span className="eyebrow">
        {proposal.category} · {proposal.confidence} confidence
        {proposal.source ? ` · ${proposal.source}` : ""}
      </span>
      <h3>{proposal.title}</h3>
      {proposal.conflicts?.length ? (
        <div className="settings-validation-message" role="alert">
          <p>
            <strong>Possible conflict with existing canon:</strong>
          </p>
          {proposal.conflicts.map((conflict) => (
            <p key={conflict}>{conflict}</p>
          ))}
        </div>
      ) : null}
      {mode === "edit" ? (
        <label>
          Edited canon summary
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
      ) : mode === "reject" ? (
        <label>
          Reason (optional)
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Why is this not canon? Helps refine future extractions."
          />
        </label>
      ) : (
        <p>{proposal.summary}</p>
      )}
      {mode === "edit" ? (
        <div className="button-row">
          <button
            disabled={!draft.trim()}
            onClick={() => onReview(proposal.id, "edit_approve", draft.trim())}
            type="button"
          >
            Save &amp; approve
          </button>
          <button
            className="secondary"
            onClick={() => {
              setMode("view");
              setDraft(proposal.summary);
            }}
            type="button"
          >
            Cancel
          </button>
        </div>
      ) : mode === "reject" ? (
        <div className="button-row">
          <button
            onClick={() =>
              onReview(proposal.id, "reject", reason.trim() || undefined)
            }
            type="button"
          >
            Confirm reject
          </button>
          <button
            className="secondary"
            onClick={() => {
              setMode("view");
              setReason("");
            }}
            type="button"
          >
            Cancel
          </button>
        </div>
      ) : (
        <div className="button-row">
          <button
            onClick={() => onReview(proposal.id, "approve")}
            type="button"
          >
            Approve
          </button>
          <button
            className="secondary"
            onClick={() => setMode("edit")}
            type="button"
          >
            Edit
          </button>
          <button
            className="secondary"
            onClick={() => setMode("reject")}
            type="button"
          >
            Reject
          </button>
        </div>
      )}
    </article>
  );
}
