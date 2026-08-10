import type { CampaignActivity, WorldCategoryId } from '../domain/worldbuilding';

// DTOs for the /v1 contract (see SOFTWARE_ARCHITECTURE.md). The mock server in
// src/mocks implements these; the real Go/Python backend will honor the same shapes.

export type ReviewAction = 'approve' | 'edit_approve' | 'reject';

export type ApiProposal = {
  id: string;
  title: string;
  category: string;
  confidence: 'High' | 'Medium' | 'Low';
  summary: string;
  source?: string;
  status: 'pending' | 'approved' | 'edited_approved' | 'rejected';
  // Contradictions the AI flagged against established canon while extracting
  // this proposal — surfaced so the GM can look closer before approving.
  conflicts?: string[];
};

export type ApiWorkspaceSummary = {
  sessionDocCount: number;
  canonMemoryCount: number;
  proposalsWaiting: number;
  recentActivity: CampaignActivity[];
};

export type ApiEntry = {
  id: string;
  category: WorldCategoryId;
  title: string;
  note: string;
  tags: string[];
};

export type ApiCanonEvent = {
  id: string;
  category: string;
  summary: string;
};

export type JobStatus = 'pending' | 'running' | 'succeeded' | 'failed';

export type JobResult = {
  proposalIds?: string[];
  outline?: string[];
  // World-build progress: categories the AI has returned so far (written
  // incrementally while the job is still running, not just at completion).
  categoriesCompleted?: string[];
  totalCategories?: number;
};

export type ApiJob = {
  id: string;
  type: string;
  status: JobStatus;
  progress: number;
  result: JobResult | null;
  error?: string | null;
};
