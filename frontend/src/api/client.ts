import type {
  CampaignListSection,
  CampaignSummary,
} from "../domain/worldbuilding";
import type {
  ApiCanonEvent,
  ApiEntry,
  ApiJob,
  ApiProposal,
  ApiWorkspaceSummary,
  ReviewAction,
} from "./types";

// Empty base = same-origin relative URLs (dev, intercepted by the MSW worker).
// Override via VITE_API_BASE to point at a real backend, or setApiBase() in tests.
let apiBase = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

// Deliberately memory-only. A BYOK credential must never be written to
// localStorage, sessionStorage, IndexedDB, or the URL. It is sent only to the
// same-origin backend for an AI job, then disappears when the page reloads or
// the user logs out. Persistent per-user credentials need real authentication
// and encrypted server-side storage, which this beta does not have yet.
let sessionOpenAIKey = "";

export function setSessionOpenAIKey(apiKey: string) {
  sessionOpenAIKey = apiKey.trim();
}

export function clearSessionAIProvider() {
  sessionOpenAIKey = "";
}

export function setApiBase(base: string) {
  apiBase = base;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  const isAIJob =
    init?.method === "POST" &&
    (path.endsWith("/notes") ||
      path.endsWith("/prep-jobs") ||
      path.endsWith("/build-world"));
  if (sessionOpenAIKey && isAIJob) {
    headers.set("X-Session-Smith-Provider", "openai");
    headers.set("X-Session-Smith-API-Key", sessionOpenAIKey);
  }
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    const failure = await response.json().catch(() => null);
    throw new Error(failure?.error?.message ?? "The request could not be completed.");
  }
  const body = await response.json();
  return body.data as T;
}

export function getCampaignSections() {
  return request<CampaignListSection[]>("/v1/campaigns");
}

export function getCampaign(campaignId: string) {
  return request<CampaignSummary>(`/v1/campaigns/${campaignId}`);
}

export function createCampaign(input: { name: string; description: string }) {
  return request<CampaignSummary>("/v1/campaigns", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateCampaign(
  campaignId: string,
  patch: { name?: string; visibility?: string; model?: string },
) {
  return request<CampaignSummary>(`/v1/campaigns/${campaignId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function getWorkspaceSummary(campaignId: string) {
  return request<ApiWorkspaceSummary>(`/v1/campaigns/${campaignId}/workspace`);
}

// Download URL for the world export (used as an <a href>, so the browser handles
// the file). format 'pdf' (default) or 'md'.
export function worldExportUrl(
  campaignId: string,
  format: "pdf" | "md" = "pdf",
) {
  return `${apiBase}/v1/campaigns/${campaignId}/world-export?format=${format}`;
}

export function listPendingProposals(campaignId: string) {
  return request<ApiProposal[]>(
    `/v1/campaigns/${campaignId}/memory-proposals?status=pending`,
  );
}

export function submitSessionNotes(
  campaignId: string,
  input: { content: string; sessionNumber: string; title: string },
) {
  return request<{ noteId: string; jobId: string; status: string }>(
    `/v1/campaigns/${campaignId}/notes`,
    {
      method: "POST",
      body: JSON.stringify({ ...input, startExtraction: true }),
    },
  );
}

export function submitPrepJob(
  campaignId: string,
  input: { goal: string; tone: string; memories: string },
) {
  return request<{ jobId: string; status: string }>(
    `/v1/campaigns/${campaignId}/prep-jobs`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}

export function listEntries(campaignId: string) {
  return request<ApiEntry[]>(`/v1/campaigns/${campaignId}/entries`);
}

export function listCanonEvents(campaignId: string) {
  return request<ApiCanonEvent[]>(`/v1/campaigns/${campaignId}/canon-events`);
}

export function createEntry(campaignId: string, entry: Omit<ApiEntry, "id">) {
  return request<ApiEntry>(`/v1/campaigns/${campaignId}/entries`, {
    method: "POST",
    body: JSON.stringify(entry),
  });
}

export function getJob(jobId: string) {
  return request<ApiJob>(`/v1/jobs/${jobId}`);
}

// Build the world once, then seal it: the GM's saved entries are extracted and
// every category the AI hasn't grounded on the GM's entries is drafted from
// scratch. Result lands as pending proposals; poll the returned jobId with pollJob.
export function submitBuildWorld(
  campaignId: string,
  input: { generateCategories: string[] },
) {
  return request<{ jobId: string; status: string }>(
    `/v1/campaigns/${campaignId}/build-world`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}

// Explicitly seal the world after reviewing the build. Read-only afterward.
export function sealWorld(campaignId: string) {
  return request<CampaignSummary>(`/v1/campaigns/${campaignId}/seal-world`, {
    method: "POST",
  });
}

export function reviewProposal(
  proposalId: string,
  action: ReviewAction,
  detail?: string,
) {
  const payload: Record<string, unknown> = { action };
  if (action === "edit_approve") payload.editedPayload = { summary: detail };
  if (action === "reject") payload.reason = detail;
  return request<{
    proposalId: string;
    status: string;
    createdCanonId?: string;
  }>(`/v1/memory-proposals/${proposalId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// Poll the async job until it settles, mirroring the 202 -> GET /v1/jobs/{id} pattern.
// onUpdate fires on every poll (not just the terminal one) so callers can show
// in-flight progress the backend writes to job.result while still running.
export async function pollJob(
  jobId: string,
  {
    intervalMs = 400,
    tries = 30,
    onUpdate,
  }: {
    intervalMs?: number;
    tries?: number;
    onUpdate?: (job: ApiJob) => void;
  } = {},
): Promise<ApiJob> {
  for (let attempt = 0; attempt < tries; attempt += 1) {
    const job = await getJob(jobId);
    onUpdate?.(job);
    if (job.status === "succeeded" || job.status === "failed") return job;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Job polling timed out");
}

export type Account = { id: string; name: string; email: string };
export type Friendship = { id: string; user: Account; status: "pending" | "accepted"; incoming: boolean };
export type CampaignInvitation = { id: string; campaignName: string; sender_name: string; role: string };
export type CampaignMembers = { members: (Account & { role: string })[]; invitations: { id: string; email: string; role: string }[] };
export const getAccount = () => request<Account>("/v1/auth/me");
export const authenticate = (register: boolean, input: { email: string; password: string; name?: string }) => request<Account>(`/v1/auth/${register ? "register" : "login"}`, { method: "POST", body: JSON.stringify(input) });
export const logout = () => request<null>("/v1/auth/logout", { method: "POST", body: "{}" });
export const listFriends = () => request<Friendship[]>("/v1/friends");
export const addFriend = (email: string) => request("/v1/friends", { method: "POST", body: JSON.stringify({ email }) });
export const acceptFriend = (id: string) => request(`/v1/friends/${id}/accept`, { method: "POST", body: "{}" });
export const removeFriend = (id: string) => request(`/v1/friends/${id}`, { method: "DELETE" });
export const listInvitations = () => request<CampaignInvitation[]>("/v1/invitations");
export const acceptInvitation = (id: string) => request(`/v1/invitations/${id}/accept`, { method: "POST", body: "{}" });
export const declineInvitation = (id: string) => request(`/v1/invitations/${id}`, { method: "DELETE" });
export const getMembers = (id: string) => request<CampaignMembers>(`/v1/campaigns/${id}/members`);
export const inviteToCampaign = (id: string, email: string, role: string) => request(`/v1/campaigns/${id}/invitations`, { method: "POST", body: JSON.stringify({ email, role }) });
export const removeCampaignMember = (id: string, memberId: string) => request(`/v1/campaigns/${id}/members/${memberId}`, { method: "DELETE" });
export const updateAccount = (patch: { name?: string; email?: string; password?: string; currentPassword?: string }) => request<Account>("/v1/auth/me", { method: "PATCH", body: JSON.stringify(patch) });
