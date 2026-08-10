import { http, HttpResponse } from 'msw';
import {
  CAMPAIGN_LISTS,
  WORLD_CATEGORIES,
  buildPrepOutline,
  extractProposalsFromNote,
  getCampaignWorkspace,
  type CampaignListSection,
  type CampaignSummary,
} from '../domain/worldbuilding';
import type { ApiCanonEvent, ApiEntry, ApiJob, ApiProposal } from '../api/types';

// Compact stand-in for backend/exporting.py build_world_export_markdown, so the
// mock export download is coherent in dev. Entries carry the snake_case id; canon
// carries the label. General Overview leads; the rest group by category.
function buildExportMarkdown(name: string, entries: ApiEntry[], canon: ApiCanonEvent[]): string {
  const overviewId = 'general_overview';
  const overviewLabel = 'General Overview';
  const lines: string[] = [`# ${name} — World Export`, '', '## World Overview', ''];

  const overview = [
    ...entries.filter((entry) => entry.category === overviewId).map((entry) => `- ${entry.title}: ${entry.note}`),
    ...canon.filter((event) => event.category === overviewLabel).map((event) => `- ${event.summary}`),
  ];
  lines.push(...(overview.length ? overview : ['No overview provided.']), '');

  lines.push('## Information provided when creating the world', '');
  WORLD_CATEGORIES.filter((category) => category.id !== overviewId).forEach((category) => {
    const items = entries.filter((entry) => entry.category === category.id);
    if (items.length === 0) return;
    lines.push(`**Category: ${category.label}**`, ...items.map((entry) => `- ${entry.title}: ${entry.note}`), '');
  });

  lines.push('## Canon by category', '');
  WORLD_CATEGORIES.filter((category) => category.label !== overviewLabel).forEach((category) => {
    const items = canon.filter((event) => event.category === category.label);
    if (items.length === 0) return;
    lines.push(`**Category: ${category.label}**`, ...items.map((event) => `- ${event.summary}`), '');
  });

  return lines.join('\n');
}

// Server-side in-memory state. This is the mock stand-in for PostgreSQL; the real
// backend replaces it while keeping the same /v1 responses.
type CampaignState = {
  proposals: ApiProposal[];
  entries: ApiEntry[];
  canon: ApiCanonEvent[];
  sessionDocCount: number;
  recentActivity: { actor: string; detail: string }[];
};

const CANON_SEED: Record<string, { category: string; summary: string }[]> = {
  campaign_ashes_of_kestrel_vale: [
    { category: 'Government Organizations', summary: 'The Iron Court sets and enforces river-crossing tariffs.' },
    { category: 'Magic Systems', summary: 'Binding oaths require a witnessed vow to hold power.' },
    { category: 'Regions', summary: 'Kestrel Vale sits downriver of the drowned bell tower.' },
    { category: 'NPCs', summary: 'Mira brokers information along the smuggling routes.' },
    { category: 'Cataclysmic Events', summary: 'The Flood of Bells reshaped the vale a generation ago.' },
  ],
};

const store = new Map<string, CampaignState>();
const jobs = new Map<string, ApiJob>();
let campaignSections: CampaignListSection[] | null = null;

let seq = 0;
const nextId = (prefix: string) => {
  seq += 1;
  return `${prefix}_${seq}`;
};

// Reset the mock server state between tests for isolation.
export function resetStore() {
  store.clear();
  jobs.clear();
  campaignSections = null;
  seq = 0;
}

// A mutable copy of the seed campaign lists so create operations persist.
function ensureSections(): CampaignListSection[] {
  if (!campaignSections) {
    campaignSections = JSON.parse(JSON.stringify(CAMPAIGN_LISTS)) as CampaignListSection[];
  }
  return campaignSections;
}

function findCampaign(campaignId: string): CampaignSummary | undefined {
  for (const section of ensureSections()) {
    const found = section.campaigns.find((campaign) => campaign.campaignId === campaignId);
    if (found) return found;
  }
  return undefined;
}

function ensureState(campaignId: string): CampaignState {
  const existing = store.get(campaignId);
  if (existing) return existing;
  const campaign = findCampaign(campaignId);
  const workspace = campaign ? getCampaignWorkspace(campaign) : null;
  const state: CampaignState = {
    proposals: (workspace?.proposals ?? []).map((proposal) => ({
      id: nextId('prop'),
      title: proposal.title,
      category: proposal.category,
      confidence: proposal.confidence,
      summary: `Proposed canon: ${proposal.title}.`,
      status: 'pending',
      conflicts: proposal.conflicts ?? [],
    })),
    entries: [],
    canon: (CANON_SEED[campaignId] ?? []).map((item) => ({ id: nextId('canon'), ...item })),
    sessionDocCount: workspace?.sessionDocCount ?? 0,
    recentActivity: workspace?.recentActivity ?? [],
  };
  store.set(campaignId, state);
  return state;
}

export const handlers = [
  http.get('*/v1/campaigns', () => HttpResponse.json({ data: ensureSections() })),

  http.post('*/v1/campaigns', async ({ request }) => {
    const body = (await request.json()) as { name?: string; description?: string };
    const name = body.name?.trim() || 'Untitled campaign';
    const campaign: CampaignSummary = {
      campaignId: nextId('campaign'),
      name,
      role: 'owner',
      status: 'planning',
      lastSessionNumber: 0,
      nextSessionLabel: 'Initial world setup incomplete',
      updatedAt: '2026-07-19T00:00:00Z',
      description: body.description?.trim() || 'New campaign world awaiting its first session.',
      worldStatus: 'draft',
    };
    const owned = ensureSections().find((section) => section.id === 'owned');
    owned?.campaigns.unshift(campaign);
    return HttpResponse.json({ data: campaign }, { status: 201 });
  }),

  http.get('*/v1/campaigns/:campaignId', ({ params }) => {
    const campaign = findCampaign(params.campaignId as string);
    if (!campaign) {
      return HttpResponse.json({ error: { code: 'campaign_not_found', message: 'Campaign not found.' } }, { status: 404 });
    }
    return HttpResponse.json({ data: campaign });
  }),

  http.patch('*/v1/campaigns/:campaignId', async ({ params, request }) => {
    const campaign = findCampaign(params.campaignId as string);
    if (!campaign) {
      return HttpResponse.json({ error: { code: 'campaign_not_found', message: 'Campaign not found.' } }, { status: 404 });
    }
    const body = (await request.json()) as { name?: string; description?: string };
    if (body.name?.trim()) campaign.name = body.name.trim();
    if (typeof body.description === 'string' && body.description.trim()) campaign.description = body.description.trim();
    return HttpResponse.json({ data: campaign });
  }),

  http.get('*/v1/campaigns/:campaignId/entries', ({ params }) => {
    const state = ensureState(params.campaignId as string);
    return HttpResponse.json({ data: state.entries });
  }),

  http.get('*/v1/campaigns/:campaignId/canon-events', ({ params }) => {
    const state = ensureState(params.campaignId as string);
    return HttpResponse.json({ data: state.canon });
  }),

  // World export. The real backend renders PDF; the mock returns the assembled
  // Markdown for either format so mock-mode dev doesn't 404 the download.
  http.get('*/v1/campaigns/:campaignId/world-export', ({ params }) => {
    const campaignId = params.campaignId as string;
    const state = ensureState(campaignId);
    const name = findCampaign(campaignId)?.name ?? campaignId;
    const markdown = buildExportMarkdown(name, state.entries, state.canon);
    return new HttpResponse(markdown, {
      headers: {
        'Content-Type': 'text/markdown; charset=utf-8',
        'Content-Disposition': `attachment; filename="${campaignId}-world.md"`,
      },
    });
  }),

  http.post('*/v1/campaigns/:campaignId/entries', async ({ params, request }) => {
    const campaign = findCampaign(params.campaignId as string);
    if (campaign?.worldStatus === 'sealed') {
      return HttpResponse.json({ error: { code: 'world_sealed', message: 'This world is sealed. Add new details through session notes.' } }, { status: 409 });
    }
    const state = ensureState(params.campaignId as string);
    const body = (await request.json()) as Omit<ApiEntry, 'id'>;
    const entry: ApiEntry = { id: nextId('entry'), category: body.category, title: body.title, note: body.note, tags: body.tags ?? [] };
    state.entries = [entry, ...state.entries];
    return HttpResponse.json({ data: entry }, { status: 201 });
  }),

  http.post('*/v1/campaigns/:campaignId/prep-jobs', async ({ request }) => {
    const body = (await request.json()) as { goal: string; tone: string };
    const jobId = nextId('job');
    const job: ApiJob = { id: jobId, type: 'generate_prep', status: 'pending', progress: 0, result: null };
    jobs.set(jobId, job);
    setTimeout(() => {
      job.status = 'succeeded';
      job.progress = 100;
      job.result = { outline: buildPrepOutline({ goal: body.goal, tone: body.tone }) };
    }, 900);
    return HttpResponse.json({ data: { jobId, status: 'pending' } }, { status: 202 });
  }),

  http.get('*/v1/campaigns/:campaignId/workspace', ({ params }) => {
    const state = ensureState(params.campaignId as string);
    return HttpResponse.json({
      data: {
        sessionDocCount: state.sessionDocCount,
        canonMemoryCount: state.canon.length,
        proposalsWaiting: state.proposals.filter((proposal) => proposal.status === 'pending').length,
        recentActivity: state.recentActivity,
      },
    });
  }),

  http.get('*/v1/campaigns/:campaignId/memory-proposals', ({ params, request }) => {
    const state = ensureState(params.campaignId as string);
    const status = new URL(request.url).searchParams.get('status');
    const data = status ? state.proposals.filter((proposal) => proposal.status === status) : state.proposals;
    return HttpResponse.json({ data });
  }),

  http.post('*/v1/campaigns/:campaignId/notes', async ({ params, request }) => {
    const campaignId = params.campaignId as string;
    ensureState(campaignId);
    const body = (await request.json()) as { content: string; sessionNumber?: string; title?: string };
    const noteId = nextId('note');
    const jobId = nextId('job');
    const source = body.title?.trim()
      ? `Session ${body.sessionNumber} — ${body.title.trim()}`
      : `Session ${body.sessionNumber}`;
    const job: ApiJob = { id: jobId, type: 'extract_canon', status: 'pending', progress: 0, result: null };
    jobs.set(jobId, job);

    // The Go/Python worker would run here; we simulate an async completion.
    setTimeout(() => {
      const state = ensureState(campaignId);
      const created: ApiProposal[] = extractProposalsFromNote(body.content).map((proposal) => ({
        id: nextId('prop'),
        title: proposal.title,
        category: proposal.category,
        confidence: proposal.confidence,
        summary: `Proposed canon: ${proposal.title}.`,
        source,
        status: 'pending',
        conflicts: [],
      }));
      state.proposals = [...created, ...state.proposals];
      job.status = 'succeeded';
      job.progress = 100;
      job.result = { proposalIds: created.map((proposal) => proposal.id) };
    }, 900);

    return HttpResponse.json({ data: { noteId, jobId, status: 'pending' } }, { status: 202 });
  }),

  http.post('*/v1/campaigns/:campaignId/build-world', ({ params }) => {
    const campaignId = params.campaignId as string;
    const campaign = findCampaign(campaignId);
    if (campaign?.worldStatus === 'sealed') {
      return HttpResponse.json({ error: { code: 'world_already_sealed', message: 'This world is sealed.' } }, { status: 409 });
    }

    const jobId = nextId('job');
    const job: ApiJob = { id: jobId, type: 'extract_memory', status: 'pending', progress: 0, result: null };
    jobs.set(jobId, job);

    // Two-pass stand-in: derive a shared anchor from the entries, then one
    // interlinked proposal per category — ALL 18, every build. Build does NOT
    // seal (that's seal-world), and is re-runnable — Regenerate replaces the
    // prior pending draft. Staged in two batches (like the real backend) so
    // the incremental-progress UI is exercisable without a real API call.
    const state = ensureState(campaignId);
    const anchorMatch = state.entries.map((entry) => entry.title).join(' ').match(/\b([A-Z][a-z]{3,}(?: [A-Z][a-z]{3,})?)\b/);
    const anchor = anchorMatch?.[1] ?? campaign?.name ?? 'the Concord';
    const expandLabels = WORLD_CATEGORIES.map((category) => category.label);
    const toProposal = (label: string): ApiProposal => ({
      id: nextId('prop'),
      title: `${label} — ${anchor}`,
      category: label,
      confidence: 'Medium',
      summary: `${label}: ${anchor} shapes this facet of the world — named institutions and figures reach into daily life, tied to the world's central tensions. (Demo build — edit or reject before it becomes canon.)`,
      source: 'World build',
      status: 'pending',
      conflicts: [],
    });

    state.proposals = state.proposals.filter((proposal) => proposal.status !== 'pending');
    const half = Math.ceil(expandLabels.length / 2);
    let created: ApiProposal[] = [];

    setTimeout(() => {
      created = expandLabels.slice(0, half).map(toProposal);
      state.proposals = [...created, ...state.proposals];
      job.status = 'running';
      job.result = { categoriesCompleted: created.map((proposal) => proposal.category), totalCategories: expandLabels.length };
    }, 500);

    setTimeout(() => {
      const secondBatch = expandLabels.slice(half).map(toProposal);
      created = [...created, ...secondBatch];
      state.proposals = [...secondBatch, ...state.proposals];
      job.status = 'succeeded';
      job.progress = 100;
      job.result = {
        proposalIds: created.map((proposal) => proposal.id),
        categoriesCompleted: created.map((proposal) => proposal.category),
        totalCategories: expandLabels.length,
      };
    }, 1000);

    return HttpResponse.json({ data: { jobId, status: 'pending' } }, { status: 202 });
  }),

  http.post('*/v1/campaigns/:campaignId/seal-world', ({ params }) => {
    const campaign = findCampaign(params.campaignId as string);
    if (!campaign) {
      return HttpResponse.json({ error: { code: 'campaign_not_found', message: 'Campaign not found.' } }, { status: 404 });
    }
    if (campaign.worldStatus === 'sealed') {
      return HttpResponse.json({ error: { code: 'world_already_sealed', message: 'This world is already sealed.' } }, { status: 409 });
    }
    campaign.worldStatus = 'sealed';
    return HttpResponse.json({ data: campaign });
  }),

  http.get('*/v1/jobs/:jobId', ({ params }) => {
    const job = jobs.get(params.jobId as string);
    if (!job) {
      return HttpResponse.json({ error: { code: 'job_not_found', message: 'Job not found.' } }, { status: 404 });
    }
    return HttpResponse.json({ data: job });
  }),

  http.patch('*/v1/memory-proposals/:proposalId', async ({ params, request }) => {
    const proposalId = params.proposalId as string;
    const body = (await request.json()) as { action: string; editedPayload?: { summary?: string }; reason?: string };
    for (const state of store.values()) {
      const proposal = state.proposals.find((candidate) => candidate.id === proposalId);
      if (!proposal) continue;
      let createdCanonId: string | undefined;
      if (body.action === 'approve' || body.action === 'edit_approve') {
        if (body.action === 'edit_approve') {
          proposal.status = 'edited_approved';
          if (body.editedPayload?.summary) proposal.summary = body.editedPayload.summary;
        } else {
          proposal.status = 'approved';
        }
        createdCanonId = nextId('canon');
        state.canon.push({ id: createdCanonId, category: proposal.category, summary: proposal.summary });
      } else {
        proposal.status = 'rejected';
      }
      return HttpResponse.json({ data: { proposalId, status: proposal.status, createdCanonId } });
    }
    return HttpResponse.json({ error: { code: 'proposal_not_found', message: 'Proposal not found.' } }, { status: 404 });
  }),
];
