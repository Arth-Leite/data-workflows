import asyncio
import os
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import aiohttp
import redis

from .constants import (
    CONCURRENCY,
    HEADERS,
    OUTPUT_DIR,
    REQUESTS_COUNT_DEFAULT,
    REQUESTS_DURATION_DEFAULT,
    WIKIPEDIA_API_PHP_URL,
)
from .utils import SlidingWindowLog, rate_limited


class WikipediaScraper:
    def __init__(self, seed_articles: list[str] | None = None) -> None:
        self.base_url = WIKIPEDIA_API_PHP_URL
        self.seed_articles = seed_articles or ["Jesus", "Python (programming language)"]

        self.__start_robots_parser()
        self.swl = SlidingWindowLog(self.requests_count, self.requests_duration, minimum_delay=1)
        self.redis = redis.Redis()
        self.redis_set = "wikipedia"

    def __start_robots_parser(self):
        self.robots_parser = RobotFileParser()
        self.robots_parser.set_url(urljoin(self.base_url, "/robots.txt"))
        self.robots_parser.read()

        if self.robots_parser.request_rate("*"):
            self.requests_count = self.robots_parser.request_rate("*").requests
            self.requests_duration = self.robots_parser.request_rate("*").seconds
        else:
            self.requests_count = REQUESTS_COUNT_DEFAULT
            self.requests_duration = REQUESTS_DURATION_DEFAULT

    async def __get_request(self, session: aiohttp.ClientSession, params: dict[str, str]) -> dict:
        async with session.get(self.base_url, params=params, headers=HEADERS) as response:
            if response.status != 200:
                response.raise_for_status()
            return await response.json()

    def __get_text_params(self, title: str) -> dict[str, str]:
        return {"action": "query", "prop": "extracts", "format": "json", "explaintext": "1", "titles": title}

    def __get_links_params(self, title: str, plcontinue: dict[str, str] | None = None) -> dict[str, str]:
        params = {"action": "query", "prop": "links", "format": "json", "pllimit": "max"} | {"titles": title}

        if plcontinue:
            return params | {"plcontinue": plcontinue["plcontinue"]}
        else:
            return params

    @rate_limited
    async def __request_text(self, session: aiohttp.ClientSession, title: str) -> None:
        if self.redis.sismember(self.redis_set, title):
            return

        response = await self.__get_request(session, params=self.__get_text_params(title))

        if "continue" in response:
            print("There is a continue on the text content response")
            print(response["query"]["pages"].values()[0]["title"])

        pages = response["query"]["pages"]
        for page in pages.values():
            title = page["title"]
            # TODO: Use non-blocking aiofiles
            with open(os.path.join(OUTPUT_DIR, f"{title}.txt"), "w") as f:
                f.write(page["extract"])

            self.redis.sadd(self.redis_set, title)

    @rate_limited
    async def __request_links(self, session: aiohttp.ClientSession, title: str):
        titles = []
        response = await self.__get_request(session, params=self.__get_links_params(title))

        pages = response["query"]["pages"]

        for page in pages.values():
            titles.extend([link["title"] for link in page["links"]])

        while "continue" in response:
            response = await self.__get_request(
                session, params=self.__get_links_params(title, plcontinue=response["continue"])
            )

            pages = response["query"]["pages"]

            for page in pages.values():
                titles.extend([link["title"] for link in page["links"]])

        return titles

    async def __crawl_worker(
        self, session: aiohttp.ClientSession, queue: asyncio.Queue, visited: set, pages_limit: int = 50
    ):
        pages_crawled = 0
        while pages_crawled < pages_limit:
            title = await queue.get()

            if title in visited:
                print(f"Page {title} has already been visited")
                continue

            await self.__request_text(session, title)
            new_titles = await self.__request_links(session, title)

            for title in new_titles:
                queue.put_nowait(title)

            pages_crawled += 1

    async def crawl(self, pages_limit: int = 5):
        queue = asyncio.Queue()
        for article in self.seed_articles:
            queue.put_nowait(article)

        visited = set()

        async with aiohttp.ClientSession() as session:
            await asyncio.gather(
                *[self.__crawl_worker(session, queue, visited, pages_limit) for _ in range(CONCURRENCY)]
            )


if __name__ == "__main__":
    wiki_crawl = WikipediaScraper()
    asyncio.run(wiki_crawl.crawl())
