create index concurrently if not exists idx_pages_claimable
on wikipedia_pages (updated_datetime)
where status in ('queued', 'pending');
