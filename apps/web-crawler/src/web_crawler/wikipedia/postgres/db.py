import asyncio
import logging
import os
from pathlib import Path

import asyncpg

SQL_DIR = Path(__file__).parent / "sql"


def read_file(file_name: str) -> str:
    return (SQL_DIR / file_name).read_text()


class WikipediaCrawlerPostgresDB:
    """
    This class should be handling everything like the pool creation, the transaction handling,
    ensuring that the DB exists and the tables exist, if not create with the propert schema
    """

    def __init__(self) -> None:
        self._setup_lock = asyncio.Lock()
        self.setup_done = False
        self.pool: asyncpg.Pool = None

    async def setup(self) -> None:
        if self.setup_done:
            return
        async with self._setup_lock:  # Ensure only one can run this at a time
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
                sql_statement = read_file("init.sql")
                await conn.execute(sql_statement)
            logging.info("WikipediaCrawlerPostgresDB: DB initiated")

            self.setup_done = True

    async def insert_row(self, page_title: str, page_id: int, page_content: str):
        await self.setup()
        async with self.pool.acquire() as conn:
            await conn.execute(
                "insert into wikipedia_pages (id, title, text_content) values ($1, $2, $3)",
                page_id,
                page_title,
                page_content,
            )

    async def read_table(self):
        await self.setup()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("select * from wikipedia_pages")

        print(rows)
