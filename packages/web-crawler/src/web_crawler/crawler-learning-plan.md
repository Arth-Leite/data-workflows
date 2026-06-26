# Distributed Web Crawler — A Phased Learning Plan

A crawler is one of the best things to build for learning because it forces you to
confront queues, idempotency, failure handling, and orchestration all in one place.
The key to not getting overwhelmed is a single principle:

> **Build the simplest thing that works end-to-end first, then replace one piece at a time.**

Don't start with the broker, DLQ, and parallelism. Start with a dumb loop and *earn*
each piece of infrastructure by feeling the pain it solves.

Each phase below has one focus, and — crucially — a list of things to **deliberately
ignore** until later.

---

## Phase 0 — Set the rules of the game

Before any code, decide two things:

1. **Your target.** Use a crawl-friendly sandbox like `books.toscrape.com` or
   `quotes.toscrape.com`. They're built for this, so you can postpone robots.txt and
   politeness worries while learning the mechanics.
2. **Your definition of "done" for v1** — e.g. *"crawl all pages under one domain, store
   each page's HTML and the links found on it."* Keep the scope tiny.

*Ignore for now:* everything else.

---

## Phase 1 — The crawl loop, single process, zero infrastructure

Write one Python script. No Docker, no broker, no DB. Just:

- a `deque` as your queue,
- a `set` of visited URLs,
- a loop that pops a URL, fetches it, parses out links, and pushes the new ones.

Print what you find.

This teaches you the actual heart of a crawler — the **frontier** (known-but-not-yet-visited
URLs) and **dedup** (don't visit the same URL twice). Everything you build later is just
this loop, distributed.

**On tooling:**

- For static HTML you do **not** need a headless browser — plain HTTP (`httpx`/`requests`)
  plus a parser (`BeautifulSoup`, `lxml`, or `selectolax`) is enough and far lighter. A
  headless browser only earns its place when content is rendered by JavaScript.
- Scrapy *is* overkill here — not because it's bad, but because it hides the exact machinery
  (scheduler, dupe filter, downloader) you're trying to learn. Build it by hand; later, read
  Scrapy's architecture docs and you'll recognize every piece.

*Ignore for now:* persistence, parallelism, errors, politeness.

---

## Phase 2 — Make it survive a restart (DuckDB)

Move the frontier and visited-set out of memory into DuckDB. Roughly two tables:

- `urls` — url, status (`pending` / `in_progress` / `done` / `failed`), discovered_at
- `pages` — url, html, fetched_at

Now your "queue" is *"SELECT a pending URL"*, and dedup is a uniqueness constraint.

The concept here is **idempotency and resumability** — you should be able to kill the script
and restart it without re-crawling or losing work.

*Ignore for now:* concurrency safety of those status updates (single process, so no race yet).

---

## Phase 3 — Be a good citizen

Now make a *correct* crawler. Add:

- per-domain delay between requests (politeness / not-DDOSing),
- a real User-Agent,
- request timeouts,
- retry-with-backoff on transient failures,
- robots.txt parsing (Python's `urllib.robotparser` is enough).

Decide what a "permanently failed" URL looks like — that distinction is what your DLQ will
key off later.

The concept: **failure is normal.** Networks flake, pages 404, servers rate-limit you. A
crawler that doesn't expect failure is a crawler that dies in five minutes.

*Ignore for now:* distributing any of this.

---

## Phase 4 — Externalize the queue (message broker + DLQ)

You now have a correct single crawler, so introduce a real broker (Redis is the lightest to
learn; RabbitMQ if you want native DLQ/routing semantics). The crawler stops reading the
frontier from DuckDB and instead **consumes** URL messages from the broker, and **publishes**
newly-found URLs back to it. Producer and consumer are now decoupled.

This is where the **DLQ** becomes concrete: a message that fails processing N times gets
routed to a separate dead-letter queue instead of being retried forever or silently dropped.

- With RabbitMQ this is largely configuration.
- With Redis you implement the retry-count-and-reroute logic yourself (a great exercise).

*Ignore for now:* multiple workers — get it working with exactly one consumer first.

---

## Phase 5 — Go parallel (Docker Compose + multiple workers)

Containerize the crawler and run several replicas via Compose, all consuming from the same
broker. The broker now naturally load-balances URLs across workers.

The hard concept this surfaces: **shared dedup.** With multiple workers, "have we seen this
URL?" can't live in one process's memory. It has to be centralized — a Redis set, your DuckDB
uniqueness constraint, or a Bloom filter. You'll also hit the "two workers grab the same URL"
race, which forces you to think about atomic claim operations.

This is the single most instructive problem in the whole project — sit with it.

*Ignore for now:* orchestration and scheduling.

---

## Phase 6 — Add Airflow for the right job

A clarification worth internalizing early: **Airflow is an orchestrator, not a runtime.**

It is the *wrong* tool to **be** the continuously-running crawl loop. It's the *right* tool to:

- kick off a crawl run by seeding the queue,
- schedule periodic re-crawls,
- run downstream DAGs that process your crawled data in DuckDB — cleaning, link-graph
  building, analytics.

Let the workers crawl continuously; let Airflow start jobs and run the batch analytics over
the results. Forcing the crawl loop into a DAG is a common mistake that fights the framework.

---

## Phase 7 — Look at what you built

Write DuckDB queries over your `pages` and `urls` tables:

- pages crawled over time,
- failure rates,
- the link graph,
- which domains dominate.

This closes the loop and is where DuckDB shines.

---

## Cross-cutting concepts to keep in your back pocket

These will recur across phases:

- **The frontier** — your set of pending URLs is the real state of the system.
- **Idempotency** — every operation should be safe to repeat.
- **Backpressure** — an unbounded queue will eventually eat all your memory; bound it.

If you follow this order, each phase produces something runnable, and you never add
infrastructure before you've felt why you need it.
