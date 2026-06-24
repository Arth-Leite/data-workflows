import asyncio
import json
import logging
from urllib.parse import urljoin

import aiofiles
import aiohttp
import tenacity
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
OUTPUT_FILE = "books.json"
SLEEP_DELAY = 1  # seconds
CONCURRENCY = 5
BATCH_SIZE = 20


semaphore_category = asyncio.Semaphore(CONCURRENCY)
semaphore_books = asyncio.Semaphore(CONCURRENCY)


@tenacity.retry(
    stop=tenacity.stop_after_attempt(2),
    wait=tenacity.wait_exponential_jitter(),
    retry=tenacity.retry_if_exception_type(aiohttp.ClientError),
    reraise=True,
)
async def fetch_url_request(session, url, semaphore):
    async def _fetch_url_request(session, url):
        await asyncio.sleep(SLEEP_DELAY)
        async with session.get(url) as response:
            if response.status != 200:
                response.raise_for_status()
            return await response.text()

    if not semaphore:
        return await _fetch_url_request(session, url)
    else:
        async with semaphore:
            return await _fetch_url_request(session, url)


async def batch_save_book_info(queue: asyncio.Queue):
    while True:
        # wait for the queue to have something on it
        first_elem = await queue.get()  # Can get stuck be careful
        if not first_elem:
            # even after await there is no item, then we finished scraping
            return
        else:
            books = [first_elem]

        for _ in range(BATCH_SIZE):
            try:
                books.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        async with aiofiles.open(OUTPUT_FILE, "a") as f:
            await f.write("\n".join(books) + "\n")

        # free the elements
        for _ in books:
            queue.task_done()


async def scrape_book_info(session, url, queue: asyncio.Queue):
    try:
        text = await fetch_url_request(session, url, semaphore_books)
    except Exception as e:
        logging.error(f"Request failed for {url}: {e}")
        return

    soup = BeautifulSoup(text, "html.parser")
    title = soup.select_one("h1")
    rating = soup.select_one(".star-rating")
    price = soup.select_one(".price_color")
    currency = soup.select_one(".price_color")
    description = soup.select_one(".product_page > p")

    # Essentials
    if not (title and price):
        logging.error(f"Invalid data for {url}")

    book = {
        "title": title.text,
        "rating": rating["class"][1],
        "price": price.text[1:],
        "currency": currency.text[0],
        "description": description.text if description else None,
    }
    await queue.put(json.dumps(book))


async def scrape_categories(session, category_url, queue):
    while True:
        try:
            text = await fetch_url_request(session, category_url, semaphore_books)
        except Exception as e:
            logging.error(f"Request failed for {category_url}: {e}")
            return

        soup = BeautifulSoup(text, "html.parser")

        books_tasks = []
        for book in soup.select("h3 a[href]"):
            book_url = urljoin(category_url, book["href"])
            books_tasks.append(
                scrape_book_info(session=session, url=book_url, queue=queue)
            )
        await asyncio.gather(*books_tasks)

        if soup.select(".next a[href]"):  # next button
            category_url = urljoin(
                category_url, soup.select(".next a[href]")[0]["href"]
            )
        else:
            return


async def main():
    category_urls = []
    queue = asyncio.Queue()

    async with aiohttp.ClientSession() as session:
        text = await fetch_url_request(session, BASE_URL, None)
        soup = BeautifulSoup(text, "html.parser")
        for cat in soup.select(".nav-list ul a"):
            category_urls.append(cat["href"])

        writer_tasks = asyncio.create_task(batch_save_book_info(queue))
        tasks = []
        for cat_url in category_urls:
            current_url = urljoin(BASE_URL, cat_url)
            tasks.append(scrape_categories(session, current_url, queue))
        await asyncio.gather(*tasks, return_exceptions=True)
        await queue.put(None)  # Unstuck the await
        await writer_tasks


asyncio.run(main())
