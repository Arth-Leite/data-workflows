create index concurrently if not exists idx_jobs_queued
on wikipedia_pages (
    updated_datetime
) where status = 'queued';
