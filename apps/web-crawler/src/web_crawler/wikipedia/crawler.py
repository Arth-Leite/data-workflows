import asyncio
import logging
import os

import aiohttp
import redis.asyncio as redis

from .constants import (
    CONCURRENCY,
    HEADERS,
    REQUESTS_COUNT_DEFAULT,
    REQUESTS_DURATION_DEFAULT,
    WIKIPEDIA_API_PHP_URL,
)
from .postgres.db import WikipediaCrawlerPostgresDB
from .utils import SlidingWindowLog, rate_limited


class WikipediaScraper:
    def __init__(self, seed_articles: list[str] | None = None) -> None:
        self.base_url = WIKIPEDIA_API_PHP_URL
        self.seed_articles = seed_articles or ["Jesus"]

        self._start_robots_parser()
        self.swl = SlidingWindowLog(self.requests_count, self.requests_duration, minimum_delay=1)

        self.redis = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"))
        self.redis_set = "wikipedia"
        logging.info("Redis set")

        self.db: WikipediaCrawlerPostgresDB | None = None

    async def _setup_db(self) -> None:
        self.db = await WikipediaCrawlerPostgresDB.create()
        logging.info("Postgres set")

    def _start_robots_parser(self):
        # self.robots_parser = RobotFileParser()
        # self.robots_parser.set_url(urljoin(self.base_url, "/robots.txt"))
        # self.robots_parser.read()
        #
        # if self.robots_parser.request_rate("*"):
        #     self.requests_count = self.robots_parser.request_rate("*").requests
        #     self.requests_duration = self.robots_parser.request_rate("*").seconds
        # else:
        self.requests_count = REQUESTS_COUNT_DEFAULT
        self.requests_duration = REQUESTS_DURATION_DEFAULT

    async def _get_request(self, session: aiohttp.ClientSession, params: dict[str, str]) -> dict:
        async with session.get(self.base_url, params=params, headers=HEADERS) as response:
            if response.status != 200:
                response.raise_for_status()
            return await response.json()

    def _get_text_params(self, title: str) -> dict[str, str]:
        return {"action": "query", "prop": "extracts", "format": "json", "explaintext": "1", "titles": title}

    def _get_links_params(self, title: str, plcontinue: dict[str, str] | None = None) -> dict[str, str]:
        params = {"action": "query", "prop": "links", "format": "json", "pllimit": "max"} | {"titles": title}

        if plcontinue:
            return params | {"plcontinue": plcontinue["plcontinue"]}
        else:
            return params

    @rate_limited
    async def _request_text(self, session: aiohttp.ClientSession, title: str) -> None:
        response = await self._get_request(session, params=self._get_text_params(title))

        if "continue" in response:
            raise NotImplementedError(
                f"Wikipedia returned a 'continue' for the text extract of {title!r} - pagination isn't handled"
            )

        pages = response["query"]["pages"]
        for page in pages.values():
            await self.db.insert_row(page_title=page["title"], page_id=page["pageid"], page_content=page["extract"])
            logging.info(f"Row inserted for page {page['title']}")

    @rate_limited
    async def _request_links(self, session: aiohttp.ClientSession, title: str):
        titles = []
        response = await self._get_request(session, params=self._get_links_params(title))

        pages = response["query"]["pages"]

        for page in pages.values():
            titles.extend([link["title"] for link in page["links"]])

        while "continue" in response:
            response = await self._get_request(
                session, params=self._get_links_params(title, plcontinue=response["continue"])
            )

            pages = response["query"]["pages"]

            for page in pages.values():
                titles.extend([link["title"] for link in page["links"]])

        return titles

    async def _crawl_worker(self, session: aiohttp.ClientSession, queue: asyncio.Queue, pages_limit: int):
        while self._pages_crawled < pages_limit:
            title = await queue.get()
            try:
                added = await self.redis.sadd(self.redis_set, title)
                if not added:
                    continue

                await self._request_text(session, title)
                new_titles = await self._request_links(session, title)

                for new_title in new_titles:
                    queue.put_nowait(new_title)

                self._pages_crawled += 1

                logging.info(f"Page {title} scraped")
            finally:
                queue.task_done()

    async def crawl(self, pages_limit: int = 50):
        await self._setup_db()

        queue = asyncio.Queue()
        for article in self.seed_articles:
            queue.put_nowait(article)

        self._pages_crawled = 0

        async with aiohttp.ClientSession() as session:
            workers = [asyncio.create_task(self._crawl_worker(session, queue, pages_limit)) for _ in range(CONCURRENCY)]

            # This will only finish once the queue has all the items marked as done
            await queue.join()

            for worker in workers:
                worker.cancel()

            # Here it waits until all the workers finish; cancellation is expected here
            await asyncio.gather(*workers, return_exceptions=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.info("Starting Wikipedia Crawler")
    wiki_crawl = WikipediaScraper()
    asyncio.run(wiki_crawl.crawl())
