import asyncio
import json
import aiofiles
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import aiohttp


BASE_URL = "https://books.toscrape.com/"
OUTPUT_FILE = "books.json"
SLEEP_DELAY = 1  # seconds
CONCURRENCY = 5
BATCH_SIZE = 20


semaphore_category = asyncio.Semaphore(CONCURRENCY)
semaphore_books = asyncio.Semaphore(CONCURRENCY)


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
                books.append(queue.get_nowait())  # blocking
            except asyncio.QueueEmpty:
                break

        async with aiofiles.open(OUTPUT_FILE, "a") as f:
            await f.write("\n".join(books) + "\n")

        # free the elements
        for _ in books:
            queue.task_done()


async def scrape_book_info(session, url, queue: asyncio.Queue):
    async with semaphore_books:
        await asyncio.sleep(SLEEP_DELAY)
        async with session.get(url) as response:
            text = await response.text()

    soup = BeautifulSoup(text, "html.parser")
    book = {
        "title": soup.select("h1")[0].text,
        "rating": soup.select(".star-rating")[0]["class"][1],
        "price": soup.select(".price_color")[0].text[1:],
        "currency": soup.select(".price_color")[0].text[0],
        "description": soup.select(".product_page > p")[0].text
        if soup.select(".product_page > p")
        else None,
    }
    await queue.put(json.dumps(book))


async def scrape_categories(session, category_url, queue):
    while True:
        async with semaphore_category:
            await asyncio.sleep(SLEEP_DELAY)
            async with session.get(category_url) as response:
                text = await response.text()

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
        async with session.get(BASE_URL) as response:
            text = await response.text()
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
