-- Allow the new 'fill_world_gaps' worker job type (World Builder gap-fill:
-- propose starter canon for empty world categories). See JobType in
-- backend/schemas.py. Postgres named the original CHECK from 002 by convention
-- (ai_jobs_job_type_check); drop and re-add it with the new value included.
ALTER TABLE ai_jobs DROP CONSTRAINT IF EXISTS ai_jobs_job_type_check;
ALTER TABLE ai_jobs ADD CONSTRAINT ai_jobs_job_type_check
    CHECK (job_type IN (
        'generate_session_prep',
        'extract_memory',
        'fill_world_gaps',
        'summarize_and_tag_session_entries'
    ));
