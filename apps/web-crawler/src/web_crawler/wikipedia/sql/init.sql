create table if not exists wikipedia_pages (
    numerical_id bigint,
    title text primary key,
    text_content text,
    updated_datetime timestamp,
    status text
);
