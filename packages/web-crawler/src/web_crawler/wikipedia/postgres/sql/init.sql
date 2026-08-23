create table if not exists wikipedia_pages (
    id bigint primary key,
    title text,
    text_content text
)
