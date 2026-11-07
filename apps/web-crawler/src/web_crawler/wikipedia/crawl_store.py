import asyncio
import os
from pathlib import Path

import asyncpg

SQL_DIR = Path(__file__).parent / "sql"


def read_file(file_name: str) -> str:
    return (SQL_DIR / file_name).read_text()


class PostgresCrawlStore:
    def __init__(self) -> None:
        super().__init__()
        self.setup_done = False
        self.pool: asyncpg.Pool = None
        self.lock = asyncio.Lock()
        self.wait_queue_drained = asyncio.Event()

    async def setup(self):
        if self.setup_done:
            return

        async with self.lock:
            if self.setup_done:
                return
            self.pool = await asyncpg.create_pool(
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
                host=os.getenv("POSTGRES_HOST"),
                database=os.getenv("POSTGRES_DB"),
                min_size=2,
                max_size=5,
            )

            async with self.pool.acquire() as conn:
                await conn.execute(read_file("init.sql"))
                await conn.execute(read_file("create_indexes.sql"))

            self.setup_done = True

    async def get_next_item(self) -> str | None:
        await self.setup()

        async with self.pool.acquire() as conn:
            sql_statement = read_file("get_next_item.sql")
            return await conn.fetchval(sql_statement)

    async def add_item_to_queue(self, title: str):
        await self.setup()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO wikipedia_pages
                VALUES (NULL, $1, NULL, now(), 'queued')
                ON CONFLICT DO NOTHING
                """,
                title,
            )

    async def set_visited(self, title):
        await self.setup()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE wikipedia_pages
                SET status = 'crawled', updated_datetime = now()
                WHERE title = $1
                """,
                title,
            )

    async def set_page_done(self, title: str):
        await self.setup()

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE wikipedia_pages
                SET status = 'done'
                WHERE title = $1
                """,
                title,
            )

            # Drained only when nothing is queued and no worker still has a page in flight
            remaining = await conn.fetchval(
                """
                SELECT count(*)
                FROM wikipedia_pages
                WHERE status IN ('queued', 'pending')
                """
            )
            if remaining == 0:
                self.wait_queue_drained.set()

    async def store_crawled_page(self, page_title: str, page_id: int, page_content: str):
        await self.setup()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE wikipedia_pages
                SET numerical_id = $1, text_content = $2
                WHERE title = $3
                """,
                page_id,
                page_content,
                page_title,
            )
