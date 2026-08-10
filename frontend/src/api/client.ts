import type { CampaignListSection, CampaignSummary } from '../domain/worldbuilding';
import type { ApiCanonEvent, ApiEntry, ApiJob, ApiProposal, ApiWorkspaceSummary, ReviewAction } from './types';

// Empty base = same-origin relative URLs (dev, intercepted by the MSW worker).
// Override via VITE_API_BASE to point at a real backend, or setApiBase() in tests.
let apiBase = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export function setApiBase(base: string) {
  apiBase = base;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`Request to ${path} failed with ${response.status}`);
  }
  const body = await response.json();
  return body.data as T;
}

export function getCampaignSections() {
  return request<CampaignListSection[]>('/v1/campaigns');
}

export function getCampaign(campaignId: string) {
  return request<CampaignSummary>(`/v1/campaigns/${campaignId}`);
}

export function createCampaign(input: { name: string; description: string }) {
  return request<CampaignSummary>('/v1/campaigns', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function updateCampaign(campaignId: string, patch: { name?: string; visibility?: string; model?: string }) {
  return request<CampaignSummary>(`/v1/campaigns/${campaignId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

export function getWorkspaceSummary(campaignId: string) {
  return request<ApiWorkspaceSummary>(`/v1/campaigns/${campaignId}/workspace`);
}

// Download URL for the world export (used as an <a href>, so the browser handles
// the file). format 'pdf' (default) or 'md'.
export function worldExportUrl(campaignId: string, format: 'pdf' | 'md' = 'pdf') {
  return `${apiBase}/v1/campaigns/${campaignId}/world-export?format=${format}`;
}

export function listPendingProposals(campaignId: string) {
  return request<ApiProposal[]>(`/v1/campaigns/${campaignId}/memory-proposals?status=pending`);
}

export function submitSessionNotes(campaignId: string, input: { content: string; sessionNumber: string; title: string }) {
  return request<{ noteId: string; jobId: string; status: string }>(`/v1/campaigns/${campaignId}/notes`, {
    method: 'POST',
    body: JSON.stringify({ ...input, startExtraction: true }),
  });
}

export function submitPrepJob(campaignId: string, input: { goal: string; tone: string; memories: string }) {
  return request<{ jobId: string; status: string }>(`/v1/campaigns/${campaignId}/prep-jobs`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function listEntries(campaignId: string) {
  return request<ApiEntry[]>(`/v1/campaigns/${campaignId}/entries`);
}

export function listCanonEvents(campaignId: string) {
  return request<ApiCanonEvent[]>(`/v1/campaigns/${campaignId}/canon-events`);
}

export function createEntry(campaignId: string, entry: Omit<ApiEntry, 'id'>) {
  return request<ApiEntry>(`/v1/campaigns/${campaignId}/entries`, {
    method: 'POST',
    body: JSON.stringify(entry),
  });
}

export function getJob(jobId: string) {
  return request<ApiJob>(`/v1/jobs/${jobId}`);
}

// Build the world once, then seal it: the GM's saved entries are extracted and
// every category the AI hasn't grounded on the GM's entries is drafted from
// scratch. Result lands as pending proposals; poll the returned jobId with pollJob.
export function submitBuildWorld(campaignId: string, input: { generateCategories: string[] }) {
  return request<{ jobId: string; status: string }>(`/v1/campaigns/${campaignId}/build-world`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

// Explicitly seal the world after reviewing the build. Read-only afterward.
export function sealWorld(campaignId: string) {
  return request<CampaignSummary>(`/v1/campaigns/${campaignId}/seal-world`, { method: 'POST' });
}

export function reviewProposal(proposalId: string, action: ReviewAction, detail?: string) {
  const payload: Record<string, unknown> = { action };
  if (action === 'edit_approve') payload.editedPayload = { summary: detail };
  if (action === 'reject') payload.reason = detail;
  return request<{ proposalId: string; status: string; createdCanonId?: string }>(`/v1/memory-proposals/${proposalId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

// Poll the async job until it settles, mirroring the 202 -> GET /v1/jobs/{id} pattern.
// onUpdate fires on every poll (not just the terminal one) so callers can show
// in-flight progress the backend writes to job.result while still running.
export async function pollJob(
  jobId: string,
  { intervalMs = 400, tries = 30, onUpdate }: { intervalMs?: number; tries?: number; onUpdate?: (job: ApiJob) => void } = {},
): Promise<ApiJob> {
  for (let attempt = 0; attempt < tries; attempt += 1) {
    const job = await getJob(jobId);
    onUpdate?.(job);
    if (job.status === 'succeeded' || job.status === 'failed') return job;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error('Job polling timed out');
}
