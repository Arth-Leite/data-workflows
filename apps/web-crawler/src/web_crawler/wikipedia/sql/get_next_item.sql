UPDATE wikipedia_pages
SET status = 'pending', updated_datetime = now()
WHERE
    title = (
        SELECT title
        FROM wikipedia_pages
        WHERE (
            status = 'queued'
            OR status = 'pending'
            AND now() - updated_datetime > interval '10 minutes'
        )
        ORDER BY updated_datetime
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
RETURNING title;
