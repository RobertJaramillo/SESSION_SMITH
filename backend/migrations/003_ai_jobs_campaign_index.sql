-- Supports GET /v1/campaigns/{campaign_id}/jobs (submission history, newest first).
CREATE INDEX ai_jobs_campaign_created_idx ON ai_jobs (campaign_id, created_at DESC);
