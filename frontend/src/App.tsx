import { useCallback, useEffect, useRef, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import { AppShell, PageHeader, StatCard } from './components/Layout';
import {
  WORLD_CATEGORIES,
  campaignWorkspaceNavItems,
  getCampaignWorkspace,
  worldCompleteness,
  type CampaignListSection,
  type CampaignSummary,
  type CampaignWorkspacePage,
} from './domain/worldbuilding';
import {
  createCampaign,
  createEntry,
  getCampaign,
  getCampaignSections,
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
  updateCampaign,
  worldExportUrl,
} from './api/client';
import type { ApiCanonEvent, ApiEntry, ApiProposal, ApiWorkspaceSummary, ReviewAction } from './api/types';

type PrepState = { goal: string; tone: string; memories: string; outline: string };
type NoteSubmission = { note: string; sessionNumber: string; title: string };

const WORKSPACE_PAGES = campaignWorkspaceNavItems.map((item) => item.page) as string[];

export default function App() {
  const startsOnDashboard = new URLSearchParams(window.location.search).get('preview') === 'dashboard';
  const [isAuthenticated, setIsAuthenticated] = useState(startsOnDashboard);

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={isAuthenticated ? <Navigate replace to="/campaigns" /> : <LoginPage onSignIn={() => setIsAuthenticated(true)} />}
        />
        <Route
          path="/campaigns"
          element={isAuthenticated ? <DashboardRoute onLogout={() => setIsAuthenticated(false)} /> : <Navigate replace to="/login" />}
        />
        <Route
          path="/campaigns/:campaignId/*"
          element={isAuthenticated ? <WorkspaceRoute /> : <Navigate replace to="/login" />}
        />
        <Route path="*" element={<Navigate replace to={isAuthenticated ? '/campaigns' : '/login'} />} />
      </Routes>
    </BrowserRouter>
  );
}

function DashboardRoute({ onLogout }: { onLogout: () => void }) {
  const navigate = useNavigate();
  return (
    <CampaignDashboardPage
      onOpenCampaign={(campaign) => navigate(`/campaigns/${campaign.campaignId}`)}
      onLogout={() => { onLogout(); navigate('/login'); }}
    />
  );
}

function WorkspaceRoute() {
  const params = useParams();
  const navigate = useNavigate();
  const campaignId = params.campaignId ?? '';
  const splat = params['*'] ?? '';
  const [campaign, setCampaign] = useState<CampaignSummary | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'missing'>('loading');

  useEffect(() => {
    let active = true;
    getCampaign(campaignId)
      .then((data) => { if (active) { setCampaign(data); setStatus('ready'); } })
      .catch(() => { if (active) setStatus('missing'); });
    return () => { active = false; };
  }, [campaignId]);

  if (status === 'missing') return <Navigate replace to="/campaigns" />;
  if (status === 'loading' || !campaign) {
    return <main className="page-panel"><p className="empty-state" role="status">Loading campaign…</p></main>;
  }

  const activePage: CampaignWorkspacePage = WORKSPACE_PAGES.includes(splat) ? (splat as CampaignWorkspacePage) : 'campaign-overview';
  return (
    <CampaignWorkspaceView
      key={campaign.campaignId}
      campaign={campaign}
      activePage={activePage}
      onNavigate={(next) => navigate(`/campaigns/${campaign.campaignId}/${next}`)}
      onBackToCampaigns={() => navigate('/campaigns')}
    />
  );
}

function CampaignWorkspaceView({ campaign, activePage, onNavigate, onBackToCampaigns }: { campaign: CampaignSummary; activePage: CampaignWorkspacePage; onNavigate: (page: CampaignWorkspacePage) => void; onBackToCampaigns: () => void }) {
  const seed = getCampaignWorkspace(campaign);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [proposals, setProposals] = useState<ApiProposal[]>([]);
  const [reviewFeedback, setReviewFeedback] = useState('');
  const [savedEntries, setSavedEntries] = useState<ApiEntry[]>([]);
  const [worldStatus, setWorldStatus] = useState<'draft' | 'sealed'>(campaign.worldStatus);
  const [building, setBuilding] = useState(false);
  const [buildFeedback, setBuildFeedback] = useState('');
  // Categories the AI has confirmed so far, written incrementally by the
  // backend while the build job is still running (see pollJob's onUpdate).
  const [buildProgress, setBuildProgress] = useState<{ completed: string[]; total: number } | null>(null);
  const [sealing, setSealing] = useState(false);
  const [canonEvents, setCanonEvents] = useState<ApiCanonEvent[]>([]);
  const [workspace, setWorkspace] = useState<ApiWorkspaceSummary | null>(null);
  const [prep, setPrep] = useState<PrepState>(() => ({
    goal: seed.prepGoal,
    tone: 'danger',
    memories: seed.prepMemoriesHint,
    outline: seed.prepOutline.join('\n'),
  }));
  const [prepGenerating, setPrepGenerating] = useState(false);

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
      .then(() => { if (active) { setLoadError(''); setLoading(false); } })
      .catch(() => { if (active) { setLoadError('Could not load this campaign workspace.'); setLoading(false); } });
    return () => { active = false; };
  }, [refresh]);

  const submitNote = async ({ note, sessionNumber, title }: NoteSubmission) => {
    if (!note.trim() || extracting) return;
    setExtracting(true);
    try {
      const { jobId } = await submitSessionNotes(campaign.campaignId, { content: note, sessionNumber, title });
      await pollJob(jobId);
      await refresh();
      onNavigate('review-queue');
    } catch {
      setReviewFeedback('Extraction failed — please try submitting again.');
    } finally {
      setExtracting(false);
    }
  };

  const handleReview = async (id: string, action: ReviewAction, detail?: string) => {
    const target = proposals.find((proposal) => proposal.id === id);
    const title = target?.title ?? 'proposal';
    try {
      await apiReviewProposal(id, action, detail);
      await refresh();
      if (action === 'reject') {
        setReviewFeedback(`Rejected: ${title}${detail ? ` — ${detail}` : ''}.`);
      } else {
        setReviewFeedback(`Added to canon: ${title}.`);
      }
    } catch {
      setReviewFeedback('That action could not be completed — please try again.');
    }
  };

  const saveEntry = async (entry: Omit<ApiEntry, 'id'>) => {
    const created = await createEntry(campaign.campaignId, entry);
    setSavedEntries((current) => [created, ...current]);
  };

  // Two-pass world build (bible -> grounded expansion). Repeatable (Regenerate);
  // does NOT seal. Results are PENDING proposals reviewed inline below — nothing
  // becomes canon without approval, and the world seals only via Seal world.
  const buildWorld = async (generateCategoryIds: string[]) => {
    if (building || worldStatus === 'sealed') return;
    setBuilding(true);
    setBuildFeedback('');
    setBuildProgress(null);
    try {
      const { jobId } = await submitBuildWorld(campaign.campaignId, { generateCategories: generateCategoryIds });
      // The build runs several sequential AI calls (a world bible, then a batch
      // per few categories, with a retry for any category a batch skips), so it
      // can take well over the default poll window — give it real headroom, and
      // surface the backend's incremental category progress as it comes in.
      const job = await pollJob(jobId, {
        intervalMs: 500,
        tries: 150,
        onUpdate: (current) => {
          if (current.result?.categoriesCompleted) {
            setBuildProgress({ completed: current.result.categoriesCompleted, total: current.result.totalCategories ?? WORLD_CATEGORIES.length });
          }
        },
      });
      await refresh();
      if (job.status === 'succeeded') {
        const count = job.result?.proposalIds?.length ?? 0;
        setBuildFeedback(
          count > 0
            ? `World built — ${count} ${count === 1 ? 'proposal is' : 'proposals are'} ready to review below. Approve what you like, then Seal world. Not happy? Regenerate.`
            : 'World built, but no proposals were generated. Try adding an entry or checking a category.',
        );
      } else {
        setBuildFeedback(`Build failed: ${job.error ?? 'the AI worker could not build the world'}.`);
      }
    } catch {
      setBuildFeedback('Build failed — please try again.');
    } finally {
      setBuilding(false);
    }
  };

  // Explicit seal after review: locks the World Builder; further change via notes.
  const sealWorldHandler = async () => {
    if (sealing || worldStatus === 'sealed') return;
    setSealing(true);
    try {
      await sealWorld(campaign.campaignId);
      await refresh();
    } catch {
      setBuildFeedback('Could not seal the world — please try again.');
    } finally {
      setSealing(false);
    }
  };

  const generatePrep = async () => {
    if (prepGenerating) return;
    setPrepGenerating(true);
    try {
      const { jobId } = await submitPrepJob(campaign.campaignId, { goal: prep.goal, tone: prep.tone, memories: prep.memories });
      const job = await pollJob(jobId);
      const outline = job.result?.outline;
      if (outline) setPrep((current) => ({ ...current, outline: outline.join('\n') }));
    } catch {
      // Keep the previous outline if generation fails.
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
      {activePage === 'campaign-overview' && <CampaignOverviewPage campaign={campaign} workspace={workspace} onNavigate={onNavigate} />}
      {activePage === 'world-builder' && (
        <WorldBuilderPage
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
      {activePage === 'session-prep' && <SessionPrepPage prep={prep} generating={prepGenerating} onChange={(patch) => setPrep((current) => ({ ...current, ...patch }))} onGenerate={generatePrep} />}
      {activePage === 'notes' && <NotesPage campaign={campaign} extracting={extracting} onSubmit={submitNote} />}
      {activePage === 'review-queue' && <ReviewQueuePage proposals={proposals} feedback={reviewFeedback} loading={loading} error={loadError} onReview={handleReview} />}
      {activePage === 'canon-browser' && <CanonBrowserPage campaignId={campaign.campaignId} />}
      {activePage === 'settings' && <SettingsPage campaign={campaign} />}
    </AppShell>
  );
}

function LoginPage({ onSignIn }: { onSignIn: () => void }) {
  const [notice, setNotice] = useState('');
  return (
    <main className="login-page">
      <section className="login-hero-panel" aria-labelledby="login-title">
        <div className="login-brand-row">
          <div className="brand-mark" aria-hidden="true">✦</div>
          <div>
            <span className="eyebrow">Session Smith</span>
            <strong>AI campaign orchestration</strong>
          </div>
        </div>

        <div className="login-copy">
          <span className="eyebrow">Private beta</span>
          <h1 id="login-title">Your living campaign memory, ready before the table sits down.</h1>
          <p>
            Sign in to organize session notes, approve AI-suggested canon, and keep every campaign world
            consistent from the first session to the last.
          </p>
        </div>

        <div className="login-preview-card" aria-label="Product preview">
          <div className="preview-toolbar">
            <span></span><span></span><span></span>
            <strong>Tonight's prep</strong>
          </div>
          <div className="preview-stack">
            <div>
              <small>Canon confidence</small>
              <strong>96%</strong>
            </div>
            <div>
              <small>Pending GM review</small>
              <strong>3 memories</strong>
            </div>
            <div>
              <small>Next session</small>
              <strong>Bell Vault Fallout</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="login-card" aria-label="Sign in form">
        <div className="login-card-header">
          <span className="eyebrow">Welcome back</span>
          <h2>Log in to your campaigns</h2>
          <p>Sign in to pick up your campaigns right where you left off.</p>
        </div>

        <form onSubmit={(event) => { event.preventDefault(); onSignIn(); }}>
          <label>
            Email address
            <input autoComplete="email" defaultValue="gm@example.com" inputMode="email" placeholder="you@example.com" type="email" />
          </label>
          <label>
            Password
            <input autoComplete="current-password" defaultValue="campaign-memory" placeholder="••••••••••••" type="password" />
          </label>
          <div className="login-options-row">
            <label className="checkbox-label">
              <input defaultChecked type="checkbox" />
              <span>Remember this device</span>
            </label>
            <button className="link-button" onClick={() => setNotice('Password reset isn’t available in the private beta yet — reach out to your beta contact.')} type="button">Forgot password?</button>
          </div>
          <button className="login-submit" type="submit">Sign in</button>
        </form>

        <div className="sso-divider"><span>or continue with</span></div>
        <div className="sso-row">
          <button className="secondary" onClick={onSignIn} type="button">Google</button>
          <button className="secondary" onClick={onSignIn} type="button">Discord</button>
        </div>

        {notice && <p className="empty-state" role="status">{notice}</p>}

        <p className="login-footnote">
          New to Session Smith? <button className="link-button" onClick={() => setNotice('Thanks for your interest — beta access is granted manually right now, so we’ll be in touch.')} type="button">Request beta access</button>
        </p>
      </section>
    </main>
  );
}

function CampaignDashboardPage({ onOpenCampaign, onLogout }: { onOpenCampaign: (campaign: CampaignSummary) => void; onLogout: () => void }) {
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [sections, setSections] = useState<CampaignListSection[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const accountName = 'DrowKiroth';
  const accountEmail = 'drowkiroth@example.com';
  const accountTier = 'Private Beta GM';

  useEffect(() => {
    let active = true;
    getCampaignSections()
      .then((data) => { if (active) { setSections(data); setLoadError(''); setLoading(false); } })
      .catch(() => { if (active) { setLoadError('Could not load your campaigns.'); setLoading(false); } });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!profileMenuOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target as Node)) {
        setProfileMenuOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setProfileMenuOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [profileMenuOpen]);

  return (
    <main className="campaign-dashboard streamlined-dashboard">
      <header className="dashboard-header">
        <div className="dashboard-header-bar">
          <div className="profile-menu-wrap" ref={profileMenuRef}>
            <button
              aria-expanded={profileMenuOpen}
              aria-haspopup="menu"
              aria-label="Open profile menu"
              className="profile-icon-button"
              onClick={() => setProfileMenuOpen((open) => !open)}
              type="button"
            >
              DK
            </button>
            {profileMenuOpen && (
              <div className="profile-menu" role="menu">
                <div className="profile-menu-account">
                  <strong>{accountName}</strong>
                  <span>{accountTier}</span>
                </div>
                <button
                  onClick={() => {
                    setSettingsOpen(true);
                    setProfileMenuOpen(false);
                  }}
                  role="menuitem"
                  type="button"
                >
                  Settings
                </button>
                <button className="secondary" onClick={onLogout} role="menuitem" type="button">Log out</button>
              </div>
            )}
          </div>

          <div className="dashboard-account-inline">
            <span className="eyebrow">Signed in as</span>
            <h2 className="account-name">{accountName}</h2>
          </div>

          <button className="create-campaign-button" onClick={() => setCreateOpen(true)} type="button">+ Create campaign</button>
        </div>

        <div className="dashboard-titleblock">
          <h1>Your campaigns</h1>
          <p>Choose a world to open, or start a new campaign.</p>
        </div>
      </header>

      {loadError && <p className="settings-validation-message" role="status">{loadError}</p>}
      {loading && !loadError && <p className="empty-state" role="status">Loading your campaigns…</p>}

      <section className="dashboard-columns" aria-label="Campaign groups">
        {sections.map((section) => (
          <section className="dashboard-column" key={section.id}>
            <div className="dashboard-column-header">
              <div>
                <h2>{section.title}</h2>
                <p>{section.subtitle}</p>
              </div>
              <span className="section-count">{section.campaigns.length}</span>
            </div>

            {section.campaigns.length === 0 && (
              <p className="empty-column">No campaigns here yet.</p>
            )}

            <div className="vertical-tile-list">
              {section.campaigns.map((campaign, index) => (
                <article className="campaign-tile" key={`${section.id}-${campaign.campaignId}-${index}`}>
                  <div className="campaign-tile-top">
                    <div className="campaign-sigil" aria-hidden="true">
                      {campaign.name.split(' ').slice(0, 2).map((word) => word[0]).join('')}
                    </div>
                    <div>
                      <h3>{campaign.name}</h3>
                      <span className={`status-badge status-${campaign.status}`}>{campaign.status}</span>
                    </div>
                  </div>
                  <p>{campaign.description}</p>
                  <div className="campaign-tile-meta">
                    <span>Session {campaign.lastSessionNumber}</span>
                    <span>{campaign.nextSessionLabel}</span>
                  </div>
                  <button onClick={() => onOpenCampaign(campaign)} type="button">Open campaign</button>
                </article>
              ))}
            </div>
          </section>
        ))}
      </section>

      {settingsOpen && (
        <SettingsModal
          accountEmail={accountEmail}
          accountName={accountName}
          accountTier={accountTier}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      {createOpen && (
        <CreateCampaignDialog
          onClose={() => setCreateOpen(false)}
          onCreate={async (name, description) => {
            const created = await createCampaign({ name, description });
            setCreateOpen(false);
            onOpenCampaign(created);
          }}
        />
      )}
    </main>
  );
}

function CreateCampaignDialog({ onClose, onCreate }: { onClose: () => void; onCreate: (name: string, description: string) => Promise<void> }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const submit = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      await onCreate(name.trim(), description.trim());
    } catch {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-labelledby="create-campaign-title" aria-modal="true" className="settings-modal setting-update-modal" role="dialog">
        <div className="settings-modal-header">
          <div>
            <span className="eyebrow">New campaign</span>
            <h2 id="create-campaign-title">Create a campaign</h2>
          </div>
          <button aria-label="Close dialog" className="modal-close-button" onClick={onClose} type="button">×</button>
        </div>
        <div className="setting-update-body">
          <label>Campaign name<input onChange={(event) => setName(event.target.value)} placeholder="e.g. Shadows of Vaeloria" value={name} /></label>
          <label>Description<textarea onChange={(event) => setDescription(event.target.value)} placeholder="A one-line premise for this world." value={description} /></label>
        </div>
        <div className="settings-confirm-actions">
          <button className="secondary" onClick={onClose} type="button">Cancel</button>
          <button disabled={!name.trim() || saving} onClick={submit} type="button">{saving ? 'Creating…' : 'Create campaign'}</button>
        </div>
      </section>
    </div>
  );
}

type EditableSettingId = 'name' | 'email' | 'password';

type SettingsRow = {
  id: EditableSettingId | 'tier';
  label: string;
  value: string;
  helper: string;
  editable: boolean;
  inputType?: 'text' | 'email' | 'password';
};

function SettingsModal({
  accountEmail,
  accountName,
  accountTier,
  onClose,
}: {
  accountEmail: string;
  accountName: string;
  accountTier: string;
  onClose: () => void;
}) {
  const [settingValues, setSettingValues] = useState<Record<EditableSettingId, string>>({
    name: accountName,
    email: accountEmail,
    password: 'Password unchanged',
  });
  const [editingSetting, setEditingSetting] = useState<SettingsRow | null>(null);

  const settingsRows: SettingsRow[] = [
    {
      id: 'name',
      label: 'User name',
      value: settingValues.name,
      helper: 'Display name shown at the top of your campaign dashboard.',
      editable: true,
      inputType: 'text',
    },
    {
      id: 'tier',
      label: 'Account tier',
      value: accountTier,
      helper: 'Current access level for Session Smith features.',
      editable: false,
    },
    {
      id: 'email',
      label: 'Email',
      value: settingValues.email,
      helper: 'Primary address used for account notices and sign in.',
      editable: true,
      inputType: 'email',
    },
    {
      id: 'password',
      label: 'Password reset',
      value: settingValues.password,
      helper: 'Enter and confirm a new password before saving.',
      editable: true,
      inputType: 'password',
    },
  ];

  const saveSetting = (settingId: EditableSettingId, value: string) => {
    setSettingValues((current) => ({ ...current, [settingId]: settingId === 'password' ? 'Password updated' : value }));
    setEditingSetting(null);
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-labelledby="settings-modal-title" aria-modal="true" className="settings-modal" role="dialog">
        <div className="settings-modal-header">
          <div>
            <span className="eyebrow">Account settings</span>
            <h2 id="settings-modal-title">Settings</h2>
          </div>
          <button aria-label="Close settings" className="modal-close-button" onClick={onClose} type="button">×</button>
        </div>

        <div className="settings-option-list">
          {settingsRows.map((row) => (
            <article className="settings-option" key={row.id}>
              <div>
                <span>{row.label}</span>
                <strong>{row.value}</strong>
                <p>{row.helper}</p>
              </div>
              {row.editable ? (
                <div className="settings-option-actions" aria-label={`${row.label} actions`}>
                  <button onClick={() => setEditingSetting(row)} type="button">Update</button>
                </div>
              ) : (
                <span className="settings-readonly-badge">Current plan</span>
              )}
            </article>
          ))}
        </div>
      </section>

      {editingSetting && editingSetting.id !== 'tier' && (
        <SettingUpdateModal
          currentValue={editingSetting.value}
          inputType={editingSetting.inputType ?? 'text'}
          label={editingSetting.label}
          onClose={() => setEditingSetting(null)}
          onSave={(value) => saveSetting(editingSetting.id as EditableSettingId, value)}
        />
      )}
    </div>
  );
}

function SettingUpdateModal({
  currentValue,
  inputType,
  label,
  onClose,
  onSave,
}: {
  currentValue: string;
  inputType: 'text' | 'email' | 'password';
  label: string;
  onClose: () => void;
  onSave: (value: string) => void;
}) {
  const [newValue, setNewValue] = useState('');
  const [confirmValue, setConfirmValue] = useState('');
  const valuesMatch = newValue.length > 0 && confirmValue.length > 0 && newValue === confirmValue;

  return (
    <div className="modal-backdrop nested-modal-backdrop" role="presentation">
      <section aria-labelledby="setting-update-title" aria-modal="true" className="settings-modal setting-update-modal" role="dialog">
        <div className="settings-modal-header">
          <div>
            <span className="eyebrow">Update setting</span>
            <h2 id="setting-update-title">Update {label}</h2>
          </div>
          <button aria-label="Close update setting" className="modal-close-button" onClick={onClose} type="button">×</button>
        </div>

        <div className="setting-update-body">
          <p>Current value: <strong>{inputType === 'password' ? 'Hidden for security' : currentValue}</strong></p>
          <label>
            New {label}
            <input
              autoComplete="off"
              onChange={(event) => setNewValue(event.target.value)}
              placeholder={`Enter new ${label.toLowerCase()}`}
              type={inputType}
              value={newValue}
            />
          </label>
          <label>
            Confirm new {label}
            <input
              autoComplete="off"
              onChange={(event) => setConfirmValue(event.target.value)}
              placeholder={`Confirm new ${label.toLowerCase()}`}
              type={inputType}
              value={confirmValue}
            />
          </label>
          {!valuesMatch && (newValue.length > 0 || confirmValue.length > 0) && (
            <p className="settings-validation-message">Both fields must be filled in and match before Save is enabled.</p>
          )}
        </div>

        <div className="settings-confirm-actions">
          <button disabled={!valuesMatch} onClick={() => onSave(newValue)} type="button">Save</button>
        </div>
      </section>
    </div>
  );
}

function CampaignOverviewPage({ campaign, workspace, onNavigate }: { campaign: CampaignSummary; workspace: ApiWorkspaceSummary | null; onNavigate: (page: CampaignWorkspacePage) => void }) {
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
        <StatCard label="Last completed session" value={`${campaign.lastSessionNumber}`} tone="good" />
        <StatCard label="AI proposals waiting" value={`${proposalsWaiting}`} tone={proposalsWaiting > 0 ? 'warn' : 'default'} />
        <StatCard label="Session docs" value={`${sessionDocCount}`} />
        <StatCard label="World categories" value={`${WORLD_CATEGORIES.length}`} />
      </div>
      <div className="two-column">
        <article className="card">
          <h3>Next best actions</h3>
          <div className="action-stack">
            <button onClick={() => onNavigate('notes')} type="button">Create next session document</button>
            <button onClick={() => onNavigate('session-prep')} type="button">Generate prep from approved memory</button>
            <button onClick={() => onNavigate('review-queue')} type="button">Review pending AI proposals</button>
          </div>
        </article>
        <article className="card timeline">
          <h3>Recent activity</h3>
          {recentActivity.length === 0 ? (
            <p className="empty-state">No activity yet. Add a session document to start building this campaign's memory.</p>
          ) : (
            recentActivity.map((item) => (
              <p key={`${item.actor}-${item.detail}`}><strong>{item.actor}:</strong> {item.detail}</p>
            ))
          )}
        </article>
      </div>
    </section>
  );
}

// Shared between the draft (in-page) and sealed (read-only) World Builder views:
// proposals from a world build are reviewed the same way, with the same handler
// and review handler as the Review Queue page, so approving here is identical to
// approving there (nothing becomes canon until approved).
function InlineWorldReview({ proposals, reviewFeedback, onReview }: { proposals: ApiProposal[]; reviewFeedback: string; onReview: (id: string, action: ReviewAction, detail?: string) => void }) {
  // Keep rendering while there's feedback so the last approval's "Added to
  // canon" message survives after the final proposal leaves the pending list.
  if (proposals.length === 0 && !reviewFeedback) return null;
  return (
    <article className="card full-card">
      <h3>Review your world proposals{proposals.length > 0 ? ` (${proposals.length})` : ''}</h3>
      {proposals.length > 0 && (
        <p className="empty-state">Approve, edit, or reject each one. Nothing becomes canon until you approve it — these also appear in the Review Queue.</p>
      )}
      {reviewFeedback && <p className="empty-state" role="status">{reviewFeedback}</p>}
      <div className="proposal-list">
        {proposals.map((proposal) => (
          <ProposalCard key={proposal.id} proposal={proposal} onReview={onReview} />
        ))}
      </div>
    </article>
  );
}

function SealedWorldView({ campaignId, completeness, total, proposals, reviewFeedback, onReview }: { campaignId: string; completeness: ReturnType<typeof worldCompleteness>; total: number; proposals: ApiProposal[]; reviewFeedback: string; onReview: (id: string, action: ReviewAction, detail?: string) => void }) {
  return (
    <section className="world-builder">
      <PageHeader
        kicker="World Builder"
        title="Your world is sealed"
        body="The initial world has been built. The World Builder is now read-only — every later change comes from Session Notes, which the AI turns into proposals for your review."
      />
      <article className="card full-card">
        <div className="world-progress">
          <h3>{completeness.builtCount}/{total} categories built</h3>
          <div className="progress-track" aria-hidden="true">
            <span className="progress-fill" style={{ width: `${(completeness.builtCount / total) * 100}%` }} />
          </div>
        </div>
        <p className="empty-state">This world is sealed. To add or change canon, submit Session Notes — the AI proposes updates and you approve them in the Review Queue.</p>
        <div className="canon-grid">
          {completeness.perCategory.map(({ category, built, entryCount, canonCount }) => (
            <span key={category.id}>
              {category.label}:{' '}
              <span className={`status-badge status-${built ? 'active' : 'paused'}`}>
                {built ? `${entryCount + canonCount} built` : 'empty'}
              </span>
            </span>
          ))}
        </div>
      </article>
      <article className="card full-card">
        <h3>Export world</h3>
        <p className="empty-state">Download the world overview, the details you provided, and the approved canon (grouped by category) — for evaluation or your records.</p>
        <div className="button-row">
          <a className="button-link" href={worldExportUrl(campaignId, 'pdf')} target="_blank" rel="noreferrer">Export world (PDF)</a>
          <a className="button-link secondary" href={worldExportUrl(campaignId, 'md')} target="_blank" rel="noreferrer">Markdown</a>
        </div>
      </article>
      <InlineWorldReview proposals={proposals} reviewFeedback={reviewFeedback} onReview={onReview} />
    </section>
  );
}

function WorldBuilderPage({
  campaignId,
  worldStatus,
  saved,
  canonEvents,
  proposals,
  onSave,
  building,
  buildFeedback,
  buildProgress,
  onBuildWorld,
  onSealWorld,
  sealing,
  onReview,
  reviewFeedback,
}: {
  campaignId: string;
  worldStatus: 'draft' | 'sealed';
  saved: ApiEntry[];
  canonEvents: ApiCanonEvent[];
  proposals: ApiProposal[];
  onSave: (entry: Omit<ApiEntry, 'id'>) => void;
  building: boolean;
  buildFeedback: string;
  buildProgress: { completed: string[]; total: number } | null;
  onBuildWorld: (generateCategoryIds: string[]) => void;
  onSealWorld: () => void;
  sealing: boolean;
  onReview: (id: string, action: ReviewAction, detail?: string) => void;
  reviewFeedback: string;
}) {
  const total = WORLD_CATEGORIES.length;
  const completeness = worldCompleteness(saved, canonEvents);

  const [activeIndex, setActiveIndex] = useState(0);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [tags, setTags] = useState('');
  const [showForm, setShowForm] = useState(false);

  // Sealed worlds are read-only; the inline review lets the GM finish approving.
  if (worldStatus === 'sealed') {
    return <SealedWorldView campaignId={campaignId} completeness={completeness} total={total} proposals={proposals} reviewFeedback={reviewFeedback} onReview={onReview} />;
  }

  const gaps = completeness.gaps;
  const activeCategory = WORLD_CATEGORIES[activeIndex];
  const activeStatus = completeness.perCategory[activeIndex];
  const activeEntries = saved.filter((entry) => entry.category === activeCategory.id);

  const canSave = title.trim().length > 0 && body.trim().length > 0;
  const clearForm = () => { setTitle(''); setBody(''); setTags(''); };

  const goTo = (index: number) => {
    setActiveIndex(((index % total) + total) % total);
    setShowForm(false);
    clearForm();
  };

  const saveEntry = () => {
    if (!canSave) return;
    onSave({
      category: activeCategory.id,
      title: title.trim(),
      note: body.trim(),
      tags: tags.split(',').map((tag) => tag.trim()).filter(Boolean),
    });
    clearForm();
    setShowForm(false);
  };

  return (
    <section className="world-builder">
      <PageHeader
        kicker="World Builder"
        title="Build your world"
        body="Step through the 18 categories and add what you know as tiles. When you build, the AI grounds every category on what you've provided and drafts the rest, so all 18 come back with cohesive, interlinked canon for you to review — then Seal world when you're happy."
      />
      <article className="card full-card">
        <div className="world-progress">
          <h3>{completeness.builtCount}/{total} categories built</h3>
          <div className="progress-track" aria-hidden="true">
            <span className="progress-fill" style={{ width: `${(completeness.builtCount / total) * 100}%` }} />
          </div>
        </div>
        {gaps.length > 0 ? (
          <p className="empty-state">Gaps still open ({gaps.length}): {gaps.map((gap) => gap.label).join(', ')}. The AI will draft canon for all of them when you build.</p>
        ) : (
          <p className="empty-state">Every category has content — you're ready to build.</p>
        )}
        <div className="button-row">
          <button disabled={building} onClick={() => onBuildWorld([])} type="button">
            {building
              ? 'Building your world…'
              : proposals.length > 0
                ? 'Regenerate world'
                : 'Build world (all 18 categories)'}
          </button>
        </div>
        <p className="empty-state">Building won't seal the world — you review the proposals first, and can add more or regenerate.</p>
        {building && (
          buildProgress ? (
            <div role="status">
              <div className="progress-track" aria-hidden="true">
                <span className="progress-fill" style={{ width: `${(buildProgress.completed.length / buildProgress.total) * 100}%` }} />
              </div>
              <p className="empty-state">
                {buildProgress.completed.length}/{buildProgress.total} categories drafted so far
                {buildProgress.completed.length > 0 ? `: ${buildProgress.completed.join(', ')}` : '…'}
              </p>
            </div>
          ) : (
            <p className="empty-state" role="status">The AI worker is developing a world bible before drafting each category…</p>
          )
        )}
        {!building && buildFeedback && <p className="empty-state" role="status">{buildFeedback}</p>}
      </article>

      {proposals.length > 0 && (
        <InlineWorldReview proposals={proposals} reviewFeedback={reviewFeedback} onReview={onReview} />
      )}
      {(proposals.length > 0 || completeness.builtCount > 0) && (
        <article className="card full-card">
          <h3>Happy with your world?</h3>
          <p className="empty-state">
            {proposals.length > 0
              ? 'Sealing locks the World Builder — after this, every change comes from Session Notes. Approve the proposals you want first (or Regenerate above).'
              : 'All proposals reviewed. Sealing locks the World Builder — after this, every change comes from Session Notes.'}
          </p>
          <div className="button-row">
            <button disabled={sealing || building} onClick={onSealWorld} type="button">
              {sealing ? 'Sealing…' : 'Seal world'}
            </button>
          </div>
        </article>
      )}

      <div className="jump-strip" role="tablist" aria-label="World categories">
        {WORLD_CATEGORIES.map((category, index) => {
          const built = completeness.perCategory[index].built;
          const active = index === activeIndex;
          const state = built ? 'built' : 'gap';
          return (
            <button
              aria-selected={active}
              className={`category-pill ${active ? 'active' : ''} ${state}`}
              key={category.id}
              onClick={() => goTo(index)}
              role="tab"
              type="button"
            >
              <span className={`pill-dot ${state}`} aria-hidden="true" />
              {category.label}
            </button>
          );
        })}
      </div>

      <div className="carousel">
        <button className="carousel-arrow" aria-label="Previous category" onClick={() => goTo(activeIndex - 1)} type="button">‹</button>
        <article className="card full-card carousel-card">
          <div className="carousel-head">
            <span className="eyebrow">{activeCategory.label} · {activeIndex + 1}/{total}</span>
            <span className={`status-badge status-${activeStatus.built ? 'active' : 'paused'}`}>{activeStatus.built ? 'built' : 'gap'}</span>
          </div>
          <h3>{activeCategory.prompt}</h3>
          <div className="example-row">
            {activeCategory.examples.map((example) => <span key={example}>{example}</span>)}
          </div>

          <div className="tile-grid">
            {activeEntries.map((entry) => (
              <article className="tile" key={entry.id}>
                <strong>{entry.title}</strong>
                <p>{entry.note}</p>
                {entry.tags.length > 0 && (
                  <div className="canon-grid">{entry.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
                )}
              </article>
            ))}
            {activeStatus.canonCount > 0 && (
              <article className="tile tile-canon">
                <strong>{activeStatus.canonCount} approved canon</strong>
                <p>This category already has approved canon — browse it in the Canon Browser.</p>
              </article>
            )}
            {!showForm && (
              <button className="tile tile-add" onClick={() => setShowForm(true)} type="button">
                + Add {activeCategory.label} detail
              </button>
            )}
          </div>

          {showForm && (
            <div className="add-form">
              <label>
                Entry title
                <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={`${activeCategory.label} entry title`} />
              </label>
              <label>
                Notes for this session document
                <textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder="Paste world setup, session notes, lore updates, NPC changes, or canon changes here." />
              </label>
              <label>
                Tags, comma separated
                <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="session_01, faction, oath_magic" />
              </label>
              <div className="button-row">
                <button disabled={!canSave} onClick={saveEntry} type="button">Save entry to this session</button>
                <button className="secondary" onClick={() => { clearForm(); setShowForm(false); }} type="button">Cancel</button>
              </div>
            </div>
          )}

          {!activeStatus.built && (
            <p className="empty-state">The AI will draft starter {activeCategory.label} canon when you build.</p>
          )}
        </article>
        <button className="carousel-arrow" aria-label="Next category" onClick={() => goTo(activeIndex + 1)} type="button">›</button>
      </div>

      {saved.length > 0 && (
        <article className="card full-card">
          <h3>Saved this session ({saved.length})</h3>
          <div className="canon-grid">
            {saved.map((entry) => (
              <span key={entry.id}>{WORLD_CATEGORIES.find((category) => category.id === entry.category)?.label ?? entry.category}: {entry.title}</span>
            ))}
          </div>
        </article>
      )}
    </section>
  );
}

function SessionPrepPage({ prep, generating, onChange, onGenerate }: { prep: PrepState; generating: boolean; onChange: (patch: Partial<PrepState>) => void; onGenerate: () => void }) {
  return (
    <section>
      <PageHeader kicker="Session Prep" title="Generate the next table-ready session" body="Draft the next session from approved canon only. Review and edit everything before you bring it to the table." />
      <div className="two-column">
        <article className="card">
          <h3>Prep controls</h3>
          <label>Session goal<input value={prep.goal} onChange={(event) => onChange({ goal: event.target.value })} placeholder="What should the next session accomplish?" /></label>
          <label>Desired tone<select value={prep.tone} onChange={(event) => onChange({ tone: event.target.value })}><option value="wonder">Wonder</option><option value="danger">Danger</option><option value="intrigue">Intrigue</option></select></label>
          <label>Use memories<textarea value={prep.memories} onChange={(event) => onChange({ memories: event.target.value })} placeholder="Which approved memories should the prep draw from?" /></label>
          <button disabled={generating} onClick={onGenerate} type="button">{generating ? 'Generating prep…' : 'Queue AI prep job'}</button>
        </article>
        <article className="card">
          <h3>Generated outline</h3>
          {generating ? (
            <p className="empty-state" role="status">Pulling approved canon and drafting an outline…</p>
          ) : prep.outline.trim() === '' ? (
            <p className="empty-state">No prep generated yet. Set a goal and queue an AI prep job to build an outline.</p>
          ) : (
            <label>
              Edit before your session
              <textarea value={prep.outline} onChange={(event) => onChange({ outline: event.target.value })} />
            </label>
          )}
        </article>
      </div>
    </section>
  );
}

function NotesPage({ campaign, extracting, onSubmit }: { campaign: CampaignSummary; extracting: boolean; onSubmit: (submission: NoteSubmission) => void }) {
  const nextSession = campaign.lastSessionNumber + 1;
  const [sessionNumber, setSessionNumber] = useState(`${nextSession}`);
  const [title, setTitle] = useState('');
  const [note, setNote] = useState('');
  const canSubmit = note.trim().length > 0 && sessionNumber.trim().length > 0 && !extracting;

  return (
    <section>
      <PageHeader kicker="Session Notes" title="Log each session as its own entry" body="Session 0 is your initial world setup; Session 1 and up capture later play. Paste your raw notes and the AI worker turns them into canon candidates for your review." />
      <article className="card full-card">
        <label>Session number<input min="0" onChange={(event) => setSessionNumber(event.target.value)} type="number" value={sessionNumber} /></label>
        <label>Session title<input onChange={(event) => setTitle(event.target.value)} placeholder={`Session ${nextSession} — short title`} value={title} /></label>
        <label>
          Raw table notes
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Paste this session's raw table notes. When you submit, the AI worker reads them and proposes canon changes for your review."
          />
        </label>
        <div className="button-row">
          <button disabled={!canSubmit} onClick={() => onSubmit({ note, sessionNumber, title })} type="button">
            {extracting ? 'Extracting canon candidates…' : 'Submit notes for AI review'}
          </button>
          <button className="secondary" disabled={extracting} onClick={() => { setNote(''); setTitle(''); }} type="button">Clear</button>
        </div>
        {extracting && <p className="empty-state" role="status">The AI worker is reading your notes and drafting proposed canon changes…</p>}
      </article>
    </section>
  );
}

function ReviewQueuePage({ proposals, feedback, loading, error, onReview }: { proposals: ApiProposal[]; feedback: string; loading: boolean; error: string; onReview: (id: string, action: ReviewAction, detail?: string) => void }) {
  return (
    <section>
      <PageHeader kicker="GM Review Queue" title="Approve, edit, or reject proposed memory" body="Nothing the AI proposes becomes canon until you approve it. Review each suggestion, then approve, edit, or reject it." />
      {feedback && <p className="empty-state" role="status">{feedback}</p>}
      {error && <p className="settings-validation-message" role="status">{error}</p>}
      {loading ? (
        <article className="card full-card">
          <p className="empty-state" role="status">Loading proposals…</p>
        </article>
      ) : proposals.length === 0 ? (
        <article className="card full-card">
          <p className="empty-state">No proposals waiting. Submit session notes and the AI will suggest canon changes here for your review.</p>
        </article>
      ) : (
        <div className="proposal-list">
          {proposals.map((proposal) => (
            <ProposalCard key={proposal.id} proposal={proposal} onReview={onReview} />
          ))}
        </div>
      )}
    </section>
  );
}

function ProposalCard({ proposal, onReview }: { proposal: ApiProposal; onReview: (id: string, action: ReviewAction, detail?: string) => void }) {
  const [mode, setMode] = useState<'view' | 'edit' | 'reject'>('view');
  const [draft, setDraft] = useState(proposal.summary);
  const [reason, setReason] = useState('');

  return (
    <article className="card proposal-card">
      <span className="eyebrow">{proposal.category} · {proposal.confidence} confidence{proposal.source ? ` · ${proposal.source}` : ''}</span>
      <h3>{proposal.title}</h3>
      {proposal.conflicts && proposal.conflicts.length > 0 && (
        <div className="settings-validation-message" role="alert">
          <p><strong>Possible conflict with existing canon:</strong></p>
          {proposal.conflicts.map((conflict) => <p key={conflict}>{conflict}</p>)}
        </div>
      )}
      {mode === 'edit' ? (
        <label>
          Edited canon summary
          <textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
        </label>
      ) : mode === 'reject' ? (
        <label>
          Reason (optional)
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why is this not canon? Helps refine future extractions." />
        </label>
      ) : (
        <p>{proposal.summary}</p>
      )}
      {mode === 'edit' ? (
        <div className="button-row">
          <button disabled={!draft.trim()} onClick={() => onReview(proposal.id, 'edit_approve', draft.trim())} type="button">Save &amp; approve</button>
          <button className="secondary" onClick={() => { setMode('view'); setDraft(proposal.summary); }} type="button">Cancel</button>
        </div>
      ) : mode === 'reject' ? (
        <div className="button-row">
          <button onClick={() => onReview(proposal.id, 'reject', reason.trim() || undefined)} type="button">Confirm reject</button>
          <button className="secondary" onClick={() => { setMode('view'); setReason(''); }} type="button">Cancel</button>
        </div>
      ) : (
        <div className="button-row">
          <button onClick={() => onReview(proposal.id, 'approve')} type="button">Approve</button>
          <button className="secondary" onClick={() => setMode('edit')} type="button">Edit</button>
          <button className="secondary" onClick={() => setMode('reject')} type="button">Reject</button>
        </div>
      )}
    </article>
  );
}

function CanonBrowserPage({ campaignId }: { campaignId: string }) {
  const [canon, setCanon] = useState<ApiCanonEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');

  useEffect(() => {
    let active = true;
    listCanonEvents(campaignId)
      .then((data) => { if (active) { setCanon(data); setLoading(false); } })
      .catch(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [campaignId]);

  const needle = query.trim().toLowerCase();
  const filtered = needle
    ? canon.filter((item) => `${item.category} ${item.summary}`.toLowerCase().includes(needle))
    : canon;

  return (
    <section>
      <PageHeader kicker="Canon Memory Browser" title="Search approved campaign truth" body="Browse the approved memory the AI is allowed to draw on when generating prep and answers." />
      <article className="card full-card">
        <label>Search canon<input onChange={(event) => setQuery(event.target.value)} placeholder="NPC, faction, region, artifact, player character..." value={query} /></label>
        {loading ? (
          <p className="empty-state" role="status">Loading canon…</p>
        ) : canon.length === 0 ? (
          <p className="empty-state">No approved canon yet. Approve proposals in the review queue to build this campaign's memory.</p>
        ) : filtered.length === 0 ? (
          <p className="empty-state" role="status">No canon matches “{query}”.</p>
        ) : (
          <>
            <p className="empty-state" role="status">Showing {filtered.length} of {canon.length} approved memories.</p>
            <div className="canon-list">
              {filtered.map((item) => (
                <article className="canon-item" key={item.id}>
                  <span className="eyebrow">{item.category}</span>
                  <p>{item.summary}</p>
                </article>
              ))}
            </div>
          </>
        )}
      </article>
    </section>
  );
}

function SettingsPage({ campaign }: { campaign: CampaignSummary }) {
  const [status, setStatus] = useState('');
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  const [name, setName] = useState(campaign.name);
  const [visibility, setVisibility] = useState('private');
  const [model, setModel] = useState('balanced');
  const [saving, setSaving] = useState(false);

  const saveSettings = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      await updateCampaign(campaign.campaignId, { name: name.trim(), visibility, model });
      setStatus('Settings saved.');
    } catch {
      setStatus('Could not save settings — please try again.');
    } finally {
      setSaving(false);
    }
  };

  const exportCampaign = () => {
    const payload = { campaign, workspace: getCampaignWorkspace(campaign), exportedAt: new Date().toISOString() };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${campaign.campaignId}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    setStatus('Exported campaign JSON to your downloads.');
  };

  const confirmArchive = () => {
    setConfirmingArchive(false);
    setStatus(`"${campaign.name}" archived. (Prototype: no data was changed.)`);
  };

  return (
    <section>
      <PageHeader kicker="Campaign Settings" title="Model, visibility, and data controls" body="Owner controls for this campaign — choose the AI model, set who can see it, and export or archive your data." />
      <div className="two-column">
        <article className="card">
          <h3>Campaign</h3>
          <label>Campaign name<input onChange={(event) => setName(event.target.value)} value={name} /></label>
          <label>Default visibility<select onChange={(event) => setVisibility(event.target.value)} value={visibility}><option value="private">Private</option><option value="shared">Shared with players</option></select></label>
          <label>Model profile<select onChange={(event) => setModel(event.target.value)} value={model}><option value="cheap">Cheap draft</option><option value="balanced">Balanced</option><option value="premium">Premium prep</option></select></label>
          <button disabled={!name.trim() || saving} onClick={saveSettings} type="button">{saving ? 'Saving…' : 'Save changes'}</button>
        </article>
        <article className="card">
          <h3>Data controls</h3>
          <p>Export a JSON snapshot of this campaign, or archive it to hide it from your active list.</p>
          <div className="button-row">
            <button onClick={exportCampaign} type="button">Export campaign JSON</button>
            <button className="secondary" onClick={() => setConfirmingArchive(true)} type="button">Archive campaign</button>
          </div>
        </article>
      </div>
      {status && <p className="empty-state" role="status">{status}</p>}

      {confirmingArchive && (
        <ConfirmDialog
          title="Archive campaign"
          body={`Archive "${campaign.name}"? You can restore it later.`}
          confirmLabel="Archive"
          onCancel={() => setConfirmingArchive(false)}
          onConfirm={confirmArchive}
        />
      )}
    </section>
  );
}

function ConfirmDialog({ title, body, confirmLabel, onCancel, onConfirm }: { title: string; body: string; confirmLabel: string; onCancel: () => void; onConfirm: () => void }) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onCancel]);

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-labelledby="confirm-dialog-title" aria-modal="true" className="settings-modal setting-update-modal" role="dialog">
        <div className="settings-modal-header">
          <div>
            <span className="eyebrow">Confirm</span>
            <h2 id="confirm-dialog-title">{title}</h2>
          </div>
          <button aria-label="Close dialog" className="modal-close-button" onClick={onCancel} type="button">×</button>
        </div>
        <div className="setting-update-body">
          <p>{body}</p>
        </div>
        <div className="settings-confirm-actions">
          <button className="secondary" onClick={onCancel} type="button">Cancel</button>
          <button onClick={onConfirm} type="button">{confirmLabel}</button>
        </div>
      </section>
    </div>
  );
}
