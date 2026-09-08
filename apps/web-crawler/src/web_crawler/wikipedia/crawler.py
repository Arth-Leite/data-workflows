import asyncio
import logging
import random

import aiohttp
from web_crawler.wikipedia.constants import (
    CONCURRENCY,
    HEADERS,
    REQUESTS_COUNT_DEFAULT,
    REQUESTS_DURATION_DEFAULT,
    WIKIPEDIA_API_PHP_URL,
)
from web_crawler.wikipedia.frontier import RabbitRedisFrontier
from web_crawler.wikipedia.postgres.db import WikipediaCrawlerPostgresDB
from web_crawler.wikipedia.utils import SlidingWindowLog, rate_limited


class WikipediaScraper:
    def __init__(self, seed_articles: list[str] | None = None) -> None:
        self.base_url = WIKIPEDIA_API_PHP_URL
        self.seed_articles = seed_articles or ["Jesus"]

        self._start_robots_parser()
        self.swl = SlidingWindowLog(self.requests_count, self.requests_duration, minimum_delay=1)

    async def _setup(self) -> None:
        self.db = await WikipediaCrawlerPostgresDB.create()
        self.frontier = RabbitRedisFrontier()

    def _start_robots_parser(self):
        # TODO: Implement a real robots parser
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

    @rate_limited
    async def _request_links(self, session: aiohttp.ClientSession, title: str) -> list[str]:
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

        # Shuffle list to avoid scraping in alphabetical order
        random.shuffle(titles)

        return titles

    async def _crawl_worker(
        self,
        session: aiohttp.ClientSession,
    ):
        while self._pages_crawled < self.pages_limit:
            title = await self.frontier.get_message()
            if not title:
                continue
            try:
                if await self.frontier.has_visited(title):
                    continue

                await self._request_text(session, title)
                new_titles = await self._request_links(session, title)

                for new_title in new_titles:
                    await self.frontier.publish_message(new_title)

                await self.frontier.mark_as_visited(title)
                self._pages_crawled += 1

                logging.info(f"Scraped {title}")

            except Exception as e:
                raise (e)
            finally:
                await self.frontier.ack_message(title)
        self.pages_limit_event.set()

    async def crawl(self, pages_limit: int = 50):
        await self._setup()

        self._pages_crawled = 0
        self.pages_limit = pages_limit

        async with aiohttp.ClientSession() as session:
            self.pages_limit_event = asyncio.Event()

            for article in self.seed_articles:
                await self.frontier.publish_message(article)

            workers = {asyncio.create_task(self._crawl_worker(session)) for _ in range(CONCURRENCY)}

            finishing_tasks = {
                asyncio.create_task(self.pages_limit_event.wait()),
                asyncio.create_task(self.frontier.wait_queue_drained.wait()),
            }
            awaitables = workers | finishing_tasks
            while True:
                done, pending = await asyncio.wait(awaitables, return_when=asyncio.FIRST_COMPLETED)
                if done.intersection(set(finishing_tasks)):
                    break

                awaitables -= done
                awaitables |= {asyncio.create_task(self._crawl_worker(session)) for _ in range(len(done))}

            for task in awaitables:
                task.cancel()

            # Here it waits until all the tasks finish
            await asyncio.gather(*awaitables, return_exceptions=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.info("Starting Wikipedia Crawler")
    wiki_crawl = WikipediaScraper()
    asyncio.run(wiki_crawl.crawl(pages_limit=20))
    logging.info("Crawler ended")


if __name__ == "__main__":
    main()
