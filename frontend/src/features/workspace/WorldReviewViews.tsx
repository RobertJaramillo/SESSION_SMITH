import { worldExportUrl } from "../../api/client";
import type { ApiProposal, ReviewAction } from "../../api/types";
import { PageHeader } from "../../components/Layout";
import { worldCompleteness } from "../../domain/worldbuilding";
import { ProposalCard } from "./ReviewQueuePage";

type ReviewHandler = (
  id: string,
  action: ReviewAction,
  detail?: string,
) => void;

export function InlineWorldReview({
  proposals,
  reviewFeedback,
  onReview,
}: {
  proposals: ApiProposal[];
  reviewFeedback: string;
  onReview: ReviewHandler;
}) {
  if (proposals.length === 0 && !reviewFeedback) return null;
  return (
    <article className="card full-card">
      <h3>
        Review your world proposals
        {proposals.length > 0 ? ` (${proposals.length})` : ""}
      </h3>
      {proposals.length > 0 && (
        <p className="empty-state">
          Approve, edit, or reject each one. Nothing becomes canon until you
          approve it — these also appear in the Review Queue.
        </p>
      )}
      {reviewFeedback && (
        <p className="empty-state" role="status">
          {reviewFeedback}
        </p>
      )}
      <div className="proposal-list">
        {proposals.map((proposal) => (
          <ProposalCard
            key={proposal.id}
            proposal={proposal}
            onReview={onReview}
          />
        ))}
      </div>
    </article>
  );
}

export function SealedWorldView({
  campaignId,
  completeness,
  total,
  proposals,
  reviewFeedback,
  onReview,
}: {
  campaignId: string;
  completeness: ReturnType<typeof worldCompleteness>;
  total: number;
  proposals: ApiProposal[];
  reviewFeedback: string;
  onReview: ReviewHandler;
}) {
  return (
    <section className="world-builder">
      <PageHeader
        kicker="World Builder"
        title="Your world is sealed"
        body="The initial world has been built. The World Builder is now read-only — every later change comes from Session Notes, which the AI turns into proposals for your review."
      />
      <article className="card full-card">
        <div className="world-progress">
          <h3>
            {completeness.builtCount}/{total} categories built
          </h3>
          <div className="progress-track" aria-hidden="true">
            <span
              className="progress-fill"
              style={{ width: `${(completeness.builtCount / total) * 100}%` }}
            />
          </div>
        </div>
        <p className="empty-state">
          This world is sealed. To add or change canon, submit Session Notes —
          the AI proposes updates and you approve them in the Review Queue.
        </p>
        <div className="canon-grid">
          {completeness.perCategory.map(
            ({ category, built, entryCount, canonCount }) => (
              <span key={category.id}>
                {category.label}:{" "}
                <span
                  className={`status-badge status-${built ? "active" : "paused"}`}
                >
                  {built ? `${entryCount + canonCount} built` : "empty"}
                </span>
              </span>
            ),
          )}
        </div>
      </article>
      <article className="card full-card">
        <h3>Export world</h3>
        <p className="empty-state">
          Download the world overview, the details you provided, and the
          approved canon (grouped by category) — for evaluation or your records.
        </p>
        <div className="button-row">
          <a
            className="button-link"
            href={worldExportUrl(campaignId, "pdf")}
            target="_blank"
            rel="noreferrer"
          >
            Export world (PDF)
          </a>
          <a
            className="button-link secondary"
            href={worldExportUrl(campaignId, "md")}
            target="_blank"
            rel="noreferrer"
          >
            Markdown
          </a>
        </div>
      </article>
      <InlineWorldReview
        proposals={proposals}
        reviewFeedback={reviewFeedback}
        onReview={onReview}
      />
    </section>
  );
}
