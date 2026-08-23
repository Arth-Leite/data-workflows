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

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @classmethod
    async def create(cls) -> "WikipediaCrawlerPostgresDB":
        pool = await cls._generate_pool()
        db = cls(pool)
        await db._db_init()
        return db

    @staticmethod
    async def _generate_pool() -> asyncpg.Pool:
        username = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASSWORD")
        host = os.getenv("POSTGRES_HOST")
        database = os.getenv("POSTGRES_DB")

        return await asyncpg.create_pool(
            dsn=f"postgresql://{username}:{password}@{host}/{database}", min_size=2, max_size=5
        )

    async def _db_init(self):
        async with self.pool.acquire() as conn:
            sql_statement = read_file("init.sql")
            await conn.execute(sql_statement)
        logging.info("WikipediaCrawlerPostgresDB: DB initiated")

    async def insert_row(self, page_title: str, page_id: int, page_content: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "insert into wikipedia_pages (id, title, text_content) values ($1, $2, $3)",
                page_id,
                page_title,
                page_content,
            )

    async def read_table(self):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("select * from wikipedia_pages")

        print(rows)


if __name__ == "__main__":
    import asyncio

    async def test_db():
        db = await WikipediaCrawlerPostgresDB.create()
        await db.insert_row("test", 1, "test")
        await db.read_table()

    asyncio.run(test_db())
