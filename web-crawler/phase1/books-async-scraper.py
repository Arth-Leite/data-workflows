import asyncio
import json
import aiofiles
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import aiohttp


BASE_URL = "https://books.toscrape.com/"
OUTPUT_FILE = "./books.json"


async def scrape_book_info(session, url, books):
    async with session.get(url) as response:
        text = await response.text()

        soup = BeautifulSoup(text, "html.parser")
        async with aiofiles.open(OUTPUT_FILE, "a") as f:
            book = {
                "title": soup.select("h1")[0].text,
                "rating": soup.select(".star-rating")[0]["class"][1],
                "price": soup.select(".price_color")[0].text[1:],
                "currency": soup.select(".price_color")[0].text[0],
                "description": soup.select(".product_page > p")[0].text
                if soup.select(".product_page > p")
                else None,
            }
            await f.write(json.dumps(book) + "\n")


async def scrape_categories(
    session, category_url, books, failed_categories, failed_books
):
    while True:
        async with session.get(category_url) as response:
            text = await response.text()
            soup = BeautifulSoup(text, "html.parser")

        for book in soup.select("h3 a[href]"):
            book_url = urljoin(category_url, book["href"])
            await scrape_book_info(session=session, url=book_url, books=books)

        if soup.select(".next a[href]"):  # next button
            category_url = urljoin(
                category_url, soup.select(".next a[href]")[0]["href"]
            )
        else:
            return


async def main():
    category_urls = []
    async with aiohttp.ClientSession() as session:
        async with session.get(BASE_URL) as response:
            text = await response.text()
            soup = BeautifulSoup(text, "html.parser")
            for cat in soup.select(".nav-list ul a"):
                category_urls.append(cat["href"])

        books = []
        failed_categories = []
        failed_books = []

        tasks = []
        for cat_url in category_urls:
            current_url = urljoin(BASE_URL, cat_url)
            tasks.append(
                scrape_categories(
                    session, current_url, books, failed_categories, failed_books
                )
            )
        await asyncio.gather(*tasks, return_exceptions=True)


asyncio.run(main())
