import os

HEADERS = {"User-Agent": "WikiProjCrawlBot/0.1 (1szhae97d@mozmail.com)", "Accept-Encoding": "gzip"}

WIKIPEDIA_API_HTML_URL = "https://en.wikipedia.org/api/rest_v1/page/html/"
WIKIPEDIA_API_PHP_URL = "https://en.wikipedia.org/w/api.php"
REQUESTS_COUNT_DEFAULT = 20
REQUESTS_DURATION_DEFAULT = 60
CONCURRENCY = 2

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/usr/src/app/crawled_data/")
os.makedirs(OUTPUT_DIR, exist_ok=True)
