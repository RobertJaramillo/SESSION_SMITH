import { PageHeader, StatCard } from "../../components/Layout";
import {
  WORLD_CATEGORIES,
  getCampaignWorkspace,
  type CampaignSummary,
  type CampaignWorkspacePage,
} from "../../domain/worldbuilding";
import type { ApiWorkspaceSummary } from "../../api/types";

export function CampaignOverviewPage({
  campaign,
  workspace,
  onNavigate,
}: {
  campaign: CampaignSummary;
  workspace: ApiWorkspaceSummary | null;
  onNavigate: (page: CampaignWorkspacePage) => void;
}) {
  const seed = getCampaignWorkspace(campaign);
  const sessionDocCount = workspace?.sessionDocCount ?? seed.sessionDocCount;
  const proposalsWaiting = workspace?.proposalsWaiting ?? 0;
  const recentActivity = workspace?.recentActivity ?? seed.recentActivity;

  return (
    <section>
      <PageHeader
        kicker="Campaign Overview"
        title="At a glance"
        body="Jump into prep, add session notes, review AI proposals, or manage approved canon."
      />
      <div className="stat-grid">
        <StatCard
          label="Last completed session"
          value={`${campaign.lastSessionNumber}`}
          tone="good"
        />
        <StatCard
          label="AI proposals waiting"
          value={`${proposalsWaiting}`}
          tone={proposalsWaiting > 0 ? "warn" : "default"}
        />
        <StatCard label="Session docs" value={`${sessionDocCount}`} />
        <StatCard
          label="World categories"
          value={`${WORLD_CATEGORIES.length}`}
        />
      </div>
      <div className="two-column">
        <article className="card">
          <h3>Next best actions</h3>
          <div className="action-stack">
            <button onClick={() => onNavigate("notes")} type="button">
              Create next session document
            </button>
            <button onClick={() => onNavigate("session-prep")} type="button">
              Generate prep from approved memory
            </button>
            <button onClick={() => onNavigate("review-queue")} type="button">
              Review pending AI proposals
            </button>
          </div>
        </article>
        <article className="card timeline">
          <h3>Recent activity</h3>
          {recentActivity.length === 0 ? (
            <p className="empty-state">
              No activity yet. Add a session document to start building this
              campaign's memory.
            </p>
          ) : (
            recentActivity.map((item) => (
              <p key={`${item.actor}-${item.detail}`}>
                <strong>{item.actor}:</strong> {item.detail}
              </p>
            ))
          )}
        </article>
      </div>
    </section>
  );
}
