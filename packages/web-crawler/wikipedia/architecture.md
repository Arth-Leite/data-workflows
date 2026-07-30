# Wikipedia Crawler — Architecture & Technology Notes

Scope: bounded crawl (~10k–100k articles), single asyncio process now, replicas later, all via
`docker compose` on macOS and Linux.

---

## The numbers that shape everything

You're on the Action API with `explaintext` + gzip, not HTML. ~17 KB of text per article ×
100k ≈ **1–2 GB total**. Bandwidth is a non-issue — under 1% of your monthly cap.

Your real budget is **wall-clock**. At ~1 req/s, 100k articles is ~28 hours. So the thing worth
optimizing is *requests per article*, not bytes. Fetching `prop=extracts|links` in one call instead
of two roughly halves the crawl. (`exlimit` batching only works with `exintro`, so full extracts
stay one title per request — no way around that.)

Two API parameters are architecture, not tuning: `plnamespace=0` keeps `Talk:`/`File:`/`Template:`
out of the frontier entirely, and `maxlag` is MediaWiki's official backpressure signal — the server
returns 503 when replication lag is high specifically to tell bots to slow down.

---

## Component map

| Store | Owns | Why it and not something else |
|---|---|---|
| **RabbitMQ** | The frontier: titles discovered but not yet fetched | Work queue with per-message ack + retry. This is the shape of the problem. |
| **Postgres** | The corpus, the link graph, the crawl event log | You want a search engine. `tsvector` + GIN *is* one. |
| **Redis** | Dedup set (hot-path membership) | O(1) "have I seen this?" shared across workers, without hitting Postgres. |

The frontier and the corpus are **different data with different lifetimes** — transient work items
versus a permanent archive. Splitting them across a broker and a database isn't over-engineering,
it's the reason each one can be simple.

---

## Why RabbitMQ (and why not Kafka)

Kafka's model is a partitioned, ordered, offset-tracked log. It has no per-message ack, no
per-message delay, and no native DLQ — you hand-build retry topics. Plus ~1 GB of JVM. A crawler
frontier is a *work queue* where individual items fail and need individually-timed retries, which is
exactly what offsets are bad at. It would read fine on a CV and teach you the wrong lessons here.

RabbitMQ gives you the semantics natively: competing consumers, explicit ack, dead-letter exchanges,
and `prefetch` as backpressure. AMQP concepts transfer everywhere. The management UI on `:15672`
matters more than it sounds — watching a message walk the retry ladder into the DLQ is the fastest
way to actually understand the model.

Use **`aio-pika`** — asyncio-native, unlike raw `pika`.

### Topology

```
                    ┌──────────────────────────────► crawl.dead   (DLQ, nothing consumes it)
                    │  x-delivery-limit exceeded
  [exchange crawl] ─┴─► crawl.frontier  (quorum, durable, DLX → crawl.dlx)
        ▲                     │ 429/503
        │                     ▼
        │             crawl.retry.10s / .60s / .300s
        └─────────────────────┘   TTL expires → dead-lettered back into `crawl`
```

Publish persistent, with **publisher confirms** on — otherwise a broker restart silently drops
in-flight messages and you'll never know. `prefetch_count` is what replaces your unbounded
`asyncio.Queue`; it's the bound that stops the frontier eating your RAM.

### The concept worth sitting with: two different retries

These get conflated constantly, and they need different machinery.

1. **Crash redelivery** — the worker dies without acking. The broker notices the channel closed and
   redelivers. Quorum queues count this in `x-delivery-count`, and `x-delivery-limit` dead-letters
   after N. You get this for free; you just have to *not ack early*.

2. **Deliberate backoff** — you got a 429. Immediate redelivery is the last thing you want. So you
   ack the original and republish into a TTL queue that dead-letters *back* into the frontier when
   it expires. Carry your own attempt counter in a header, since a republished message is a new
   message and the broker's count resets.

> **The trap:** don't reach for per-message TTL (the AMQP `expiration` property) to get true
> jittered delays. RabbitMQ only expires messages from the **head** of a queue — one message with a
> 300 s TTL at the front blocks a 10 s message queued behind it. A ladder of fixed-TTL queues avoids
> this completely. You lose jitter, but jitter exists to prevent thundering herds against a shared
> target, and a global rate limiter already does that job. If you genuinely need per-message delays
> later, `rabbitmq_delayed_message_exchange` is the correct answer.

---

## Why Postgres

Given "I want a search engine with indexes later", this isn't close. A generated `tsvector` column
with a GIN index gives you real ranked full-text search, and `pg_trgm` gives you fuzzy title
matching. Columnar files (DuckDB/Parquet) would be lighter and better at analytics, but they give
you nothing for search, and you'd migrate within a month.

It's also not heavy: `postgres:17-alpine` idles around 50 MB.

**Storage reality:** Postgres TOASTs and compresses any text over ~2 KB automatically, so ~1.7 GB of
extracts lands around 600–700 MB. Setting `lz4` compression on the text column trades a little ratio
for faster decompression. Budget roughly +40% again for the GIN index.

**One schema decision that actually matters:** normalize the link graph. ~100 links/article × 100k
articles is **~10M rows**. Storing `(from_title text, to_title text)` puts you well over a GB;
a `titles(id, title)` map plus `links(from_id, to_id)` as bigints is ~500 MB. The titles table also
naturally holds targets you've *discovered but not crawled*, which turns out to be the most useful
table you have — it's both your ID map and your "what's left" view.

Keep an append-only **crawl event log** (outcome, status code, attempt number, timestamp). Failure
rates over time are the analytics you'll actually want, and the broker can't answer that — messages
are gone once acked.

Use raw **`asyncpg`**, not an ORM. Bulk inserts via `copy_records_to_table` are dramatically faster,
and writing the SQL is the point. Pair with **Alembic** for migrations, since the schema will grow
as the search side does.

---

## Redis: two things

**Enable AOF.** Your compose file mounts a volume but runs default persistence, which is RDB
snapshots only — a crash loses recent dedup state. `--appendonly yes` is the whole fix, and it
matters more once Redis is load-bearing.

**Seen ≠ stored.** These want to be two different sets. "Ever enqueued" is checked *before*
publishing and is what stops the frontier exploding. "Successfully written to Postgres" is what
stops re-fetching. If one set does both jobs, a failed write marks a page permanently done and you
never retry it. (Postgres's `UNIQUE(title)` + `ON CONFLICT` is the real idempotency guarantee;
Redis is just the fast filter in front of it.)

At much larger scale a Bloom filter replaces the set — not needed at 100k.

---

## What breaks when you add replicas

Almost nothing: RabbitMQ round-robins across competing consumers, and dedup is already centralized.

The exception is the **rate limiter**. `SlidingWindowLog` is per-process, so three replicas means 3×
the request rate at Wikipedia — which is how you get blocked. It has to become a shared token bucket
in Redis, atomic via a small Lua script. This is the same "shared state" lesson as the dedup set, and
it's the most instructive problem in the project.

Worth knowing: `minimum_delay=1` currently serializes everything to ~1 req/s, which makes
`CONCURRENCY=2` a no-op. Once failures are handled properly you can raise it — the Action API
tolerates several req/s from a well-identified bot — as long as you keep `maxlag` and honour
`Retry-After`.

---

## Reproducibility

Four services: `postgres`, `rabbitmq`, `redis`, `crawler`. The two things that make it actually
portable to your Linux box:

- **Healthchecks + `depends_on: condition: service_healthy`.** Without them the crawler races the
  broker on cold start — the classic "works the second time" bug.
- **No host paths, all config from env.** The hardcoded absolute `OUTPUT_DIR` in `constants.py` is
  the current blocker.

---

## Suggested order

Correctness first, then durability, then scale — earn each piece of infrastructure by feeling the
pain it solves:

1. Config from env; one API call for text+links; real 429/5xx handling with a
   retryable-vs-permanent distinction. **No new infra.** That distinction is what the DLQ keys off,
   so it has to exist before the broker is worth adding.
2. Postgres + schema + Alembic; backfill the existing `crawled_data/` files.
3. RabbitMQ frontier, ack/retry ladder/DLQ. Test by killing the crawler mid-run.
4. Compose it all with healthchecks.
5. Shared rate limiter → scale to N workers.
6. FTS, link graph, analytics.

Also: `crawled_data/` is currently staged in git — worth a `.gitignore` entry before it grows.
