import asyncio
import ssl
from urllib.parse import urljoin

import aiohttp
import certifi
from bs4 import BeautifulSoup

visited_urls = set()


async def _crawl_page(session: aiohttp.ClientSession, queue: asyncio.Queue):
    page_url = await queue.get()

    if page_url in visited_urls:
        queue.task_done()
        return

    await asyncio.sleep(1)
    async with session.get(page_url) as response:
        if response.status != 200:
            response.raise_for_status()

        text = await response.text()
        soup = BeautifulSoup(text, "html.parser")
        for a in soup.find_all("a"):
            link = urljoin(page_url, a["href"])
            if link not in visited_urls:
                await queue.put(link)

    visited_urls.add(page_url)
    queue.task_done()
    print("Crawler dimissed")


async def crawl_pages(session, queue):
    while True:
        await _crawl_page(session, queue)


async def main():
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        q = asyncio.Queue()
        q.put_nowait("https://books.toscrape.com/")

        task = asyncio.create_task(crawl_pages(session, q))

        await q.join()
        task.cancel()

        print(len(visited_urls))


if __name__ == "__main__":
    asyncio.run(main())
