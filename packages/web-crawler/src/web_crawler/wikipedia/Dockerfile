FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir aiohttp==3.14.1 redis==8.0.1

RUN mkdir -p web_crawler/wikipedia && touch web_crawler/__init__.py web_crawler/wikipedia/__init__.py

COPY constants.py crawler.py utils.py web_crawler/wikipedia/

