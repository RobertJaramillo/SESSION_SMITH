import { useCallback, useEffect, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { AppShell } from "../components/Layout";
import { CampaignDashboardPage as CampaignDashboard } from "../pages/CampaignDashboardPage";
import { CampaignOverviewPage as CampaignOverview } from "../features/workspace/CampaignOverviewPage";
import { NotesPage as SessionNotesPage } from "../features/workspace/NotesPage";
import { ReviewQueuePage as CampaignReviewQueuePage } from "../features/workspace/ReviewQueuePage";
import {
  SessionPrepPage as CampaignSessionPrepPage,
  type PrepState,
} from "../features/workspace/SessionPrepPage";
import { CanonBrowserPage as CampaignCanonBrowserPage } from "../features/workspace/CanonBrowserPage";
import { CampaignSettingsPage } from "../features/workspace/CampaignSettingsPage";
import { WorldBuilderPage as CampaignWorldBuilderPage } from "../features/workspace/WorldBuilderPage";
import {
  describeBuildFailure,
  describePrepFailure,
  type BuildFeedback,
} from "../features/workspace/buildFeedback";
import {
  WORLD_CATEGORIES,
  campaignWorkspaceNavItems,
  getCampaignWorkspace,
  type CampaignSummary,
  type CampaignWorkspacePage,
} from "../domain/worldbuilding";
import {
  createEntry,
  getCampaign,
  getWorkspaceSummary,
  listCanonEvents,
  listEntries,
  listPendingProposals,
  pollJob,
  reviewProposal as apiReviewProposal,
  sealWorld,
  submitBuildWorld,
  submitPrepJob,
  submitSessionNotes,
} from "../api/client";
import type {
  ApiCanonEvent,
  ApiEntry,
  ApiProposal,
  ApiWorkspaceSummary,
  ReviewAction,
} from "../api/types";
import type { AIProvider } from "../types/providers";

type NoteSubmission = { note: string; sessionNumber: string; title: string };
const WORKSPACE_PAGES = campaignWorkspaceNavItems.map(
  (item) => item.page,
) as string[];

export function DashboardRoute({
  onLogout,
  provider,
  onManageProvider,
}: {
  onLogout: () => void;
  provider: AIProvider;
  onManageProvider: () => void;
}) {
  const navigate = useNavigate();
  return (
    <CampaignDashboard
      onOpenCampaign={(campaign) =>
        navigate(`/campaigns/${campaign.campaignId}`)
      }
      onLogout={() => {
        onLogout();
        navigate("/login");
      }}
      provider={provider}
      onManageProvider={onManageProvider}
    />
  );
}

export function WorkspaceRoute() {
  const params = useParams();
  const navigate = useNavigate();
  const campaignId = params.campaignId ?? "";
  const splat = params["*"] ?? "";
  const [campaign, setCampaign] = useState<CampaignSummary | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "missing">(
    "loading",
  );

  useEffect(() => {
    let active = true;
    getCampaign(campaignId)
      .then((data) => {
        if (active) {
          setCampaign(data);
          setStatus("ready");
        }
      })
      .catch(() => {
        if (active) setStatus("missing");
      });
    return () => {
      active = false;
    };
  }, [campaignId]);

  if (status === "missing") return <Navigate replace to="/campaigns" />;
  if (status === "loading" || !campaign) {
    return (
      <main className="page-panel">
        <p className="empty-state" role="status">
          Loading campaign…
        </p>
      </main>
    );
  }

  const activePage: CampaignWorkspacePage = WORKSPACE_PAGES.includes(splat)
    ? (splat as CampaignWorkspacePage)
    : "campaign-overview";
  return (
    <CampaignWorkspaceView
      key={campaign.campaignId}
      campaign={campaign}
      activePage={activePage}
      onNavigate={(next) =>
        navigate(`/campaigns/${campaign.campaignId}/${next}`)
      }
      onBackToCampaigns={() => navigate("/campaigns")}
    />
  );
}

function CampaignWorkspaceView({
  campaign,
  activePage,
  onNavigate,
  onBackToCampaigns,
}: {
  campaign: CampaignSummary;
  activePage: CampaignWorkspacePage;
  onNavigate: (page: CampaignWorkspacePage) => void;
  onBackToCampaigns: () => void;
}) {
  const seed = getCampaignWorkspace(campaign);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [proposals, setProposals] = useState<ApiProposal[]>([]);
  const [reviewFeedback, setReviewFeedback] = useState("");
  const [savedEntries, setSavedEntries] = useState<ApiEntry[]>([]);
  const [worldStatus, setWorldStatus] = useState<"draft" | "sealed">(
    campaign.worldStatus,
  );
  const [building, setBuilding] = useState(false);
  const [buildFeedback, setBuildFeedback] = useState<BuildFeedback | null>(
    null,
  );
  // Categories the AI has confirmed so far, written incrementally by the
  // backend while the build job is still running (see pollJob's onUpdate).
  const [buildProgress, setBuildProgress] = useState<{
    completed: string[];
    total: number;
  } | null>(null);
  const [sealing, setSealing] = useState(false);
  const [canonEvents, setCanonEvents] = useState<ApiCanonEvent[]>([]);
  const [workspace, setWorkspace] = useState<ApiWorkspaceSummary | null>(null);
  const [prep, setPrep] = useState<PrepState>(() => ({
    goal: seed.prepGoal,
    tone: "danger",
    memories: seed.prepMemoriesHint,
    outline: seed.prepOutline.join("\n"),
  }));
  const [prepGenerating, setPrepGenerating] = useState(false);
  const [prepFeedback, setPrepFeedback] = useState<BuildFeedback | null>(null);

  const refresh = useCallback(async () => {
    const [pending, entries, summary, canon, fresh] = await Promise.all([
      listPendingProposals(campaign.campaignId),
      listEntries(campaign.campaignId),
      getWorkspaceSummary(campaign.campaignId),
      listCanonEvents(campaign.campaignId),
      getCampaign(campaign.campaignId),
    ]);
    setProposals(pending);
    setSavedEntries(entries);
    setWorkspace(summary);
    setCanonEvents(canon);
    // Keep the world lifecycle in sync so the World Builder switches to its
    // read-only view once a build seals the campaign server-side.
    setWorldStatus(fresh.worldStatus);
  }, [campaign.campaignId]);

  useEffect(() => {
    let active = true;
    // Async fetch effect: state updates happen after await, not synchronously.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh()
      .then(() => {
        if (active) {
          setLoadError("");
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setLoadError("Could not load this campaign workspace.");
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [refresh]);

  const submitNote = async ({ note, sessionNumber, title }: NoteSubmission) => {
    if (!note.trim() || extracting) return;
    setExtracting(true);
    try {
      const { jobId } = await submitSessionNotes(campaign.campaignId, {
        content: note,
        sessionNumber,
        title,
      });
      await pollJob(jobId);
      await refresh();
      onNavigate("review-queue");
    } catch {
      setReviewFeedback("Extraction failed — please try submitting again.");
    } finally {
      setExtracting(false);
    }
  };

  const handleReview = async (
    id: string,
    action: ReviewAction,
    detail?: string,
  ) => {
    const target = proposals.find((proposal) => proposal.id === id);
    const title = target?.title ?? "proposal";
    try {
      await apiReviewProposal(id, action, detail);
      await refresh();
      if (action === "reject") {
        setReviewFeedback(`Rejected: ${title}${detail ? ` — ${detail}` : ""}.`);
      } else {
        setReviewFeedback(`Added to canon: ${title}.`);
      }
    } catch {
      setReviewFeedback(
        "That action could not be completed — please try again.",
      );
    }
  };

  const saveEntry = async (entry: Omit<ApiEntry, "id">) => {
    const created = await createEntry(campaign.campaignId, entry);
    setSavedEntries((current) => [created, ...current]);
  };

  // Two-pass world build (bible -> grounded expansion). Repeatable (Regenerate);
  // does NOT seal. Results are PENDING proposals reviewed inline below — nothing
  // becomes canon without approval, and the world seals only via Seal world.
  const buildWorld = async (generateCategoryIds: string[]) => {
    if (building || worldStatus === "sealed") return;
    setBuilding(true);
    setBuildFeedback(null);
    setBuildProgress(null);
    try {
      const { jobId } = await submitBuildWorld(campaign.campaignId, {
        generateCategories: generateCategoryIds,
      });
      // The build runs several sequential AI calls (a world bible, then a batch
      // per few categories, with a retry for any category a batch skips), so it
      // can take well over the default poll window — give it real headroom, and
      // surface the backend's incremental category progress as it comes in.
      const job = await pollJob(jobId, {
        intervalMs: 500,
        tries: 150,
        onUpdate: (current) => {
          if (current.result?.categoriesCompleted) {
            setBuildProgress({
              completed: current.result.categoriesCompleted,
              total: current.result.totalCategories ?? WORLD_CATEGORIES.length,
            });
          }
        },
      });
      await refresh();
      if (job.status === "succeeded") {
        const count = job.result?.proposalIds?.length ?? 0;
        setBuildFeedback({
          kind: "success",
          title: "World build complete",
          message:
            count > 0
              ? `${count} ${count === 1 ? "proposal is" : "proposals are"} ready to review. Approve what you like, then seal the world when you are happy.`
              : "No proposals were generated. Try adding an entry or checking a category, then build again.",
        });
      } else {
        setBuildFeedback(describeBuildFailure(job.error));
      }
    } catch (error) {
      setBuildFeedback(
        describeBuildFailure(error instanceof Error ? error.message : null),
      );
    } finally {
      setBuilding(false);
    }
  };

  // Explicit seal after review: locks the World Builder; further change via notes.
  const sealWorldHandler = async () => {
    if (sealing || worldStatus === "sealed") return;
    setSealing(true);
    try {
      await sealWorld(campaign.campaignId);
      await refresh();
    } catch {
      setBuildFeedback({
        kind: "error",
        title: "We could not seal this world",
        message: "Your world remains editable and no data was locked.",
        guidance: "Try again in a moment. If it keeps happening, check the API service logs.",
      });
    } finally {
      setSealing(false);
    }
  };

  const generatePrep = async () => {
    if (prepGenerating) return;
    setPrepGenerating(true);
    setPrepFeedback(null);
    try {
      const { jobId } = await submitPrepJob(campaign.campaignId, {
        goal: prep.goal,
        tone: prep.tone,
        memories: prep.memories,
      });
      const job = await pollJob(jobId);
      if (job.status === "failed") {
        setPrepFeedback(describePrepFailure(job.error));
        return;
      }
      const outline = job.result?.outline;
      if (outline) {
        setPrep((current) => ({ ...current, outline: outline.join("\n") }));
        setPrepFeedback({
          kind: "success",
          title: "Session prep is ready",
          message: "Review and edit the outline before you bring it to the table.",
        });
      } else {
        setPrepFeedback(describePrepFailure(null));
      }
    } catch (error) {
      setPrepFeedback(
        describePrepFailure(error instanceof Error ? error.message : null),
      );
    } finally {
      setPrepGenerating(false);
    }
  };

  return (
    <AppShell
      activePage={activePage}
      campaignName={campaign.name}
      onBackToCampaigns={onBackToCampaigns}
      onNavigate={onNavigate}
    >
      {activePage === "campaign-overview" && (
        <CampaignOverview
          campaign={campaign}
          workspace={workspace}
          onNavigate={onNavigate}
        />
      )}
      {activePage === "world-builder" && (
        <CampaignWorldBuilderPage
          campaignId={campaign.campaignId}
          worldStatus={worldStatus}
          saved={savedEntries}
          canonEvents={canonEvents}
          proposals={proposals}
          onSave={saveEntry}
          building={building}
          buildFeedback={buildFeedback}
          buildProgress={buildProgress}
          onBuildWorld={buildWorld}
          onSealWorld={sealWorldHandler}
          sealing={sealing}
          onReview={handleReview}
          reviewFeedback={reviewFeedback}
        />
      )}
      {activePage === "session-prep" && (
        <CampaignSessionPrepPage
          prep={prep}
          generating={prepGenerating}
          feedback={prepFeedback}
          onChange={(patch) => setPrep((current) => ({ ...current, ...patch }))}
          onGenerate={generatePrep}
        />
      )}
      {activePage === "notes" && (
        <SessionNotesPage
          campaign={campaign}
          extracting={extracting}
          onSubmit={submitNote}
        />
      )}
      {activePage === "review-queue" && (
        <CampaignReviewQueuePage
          proposals={proposals}
          feedback={reviewFeedback}
          loading={loading}
          error={loadError}
          onReview={handleReview}
        />
      )}
      {activePage === "canon-browser" && (
        <CampaignCanonBrowserPage campaignId={campaign.campaignId} />
      )}
      {activePage === "settings" && (
        <CampaignSettingsPage campaign={campaign} />
      )}
    </AppShell>
  );
}
