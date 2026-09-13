# Real-Time Market Data Dashboard

A full-stack pipeline that streams live equity quotes and trades from Alpaca, persists them to SQLite, and outputs them to a React Dashboard.

**Status:** Deployed on [Railway](https://stef-market-dashboard.up.railway.app/). More features are planned for the future, see roadmap for specifics.

## Architecture

Alpaca WebSocket -> asyncio queue -> batched SQLite writes -> FastAPI -> WS broadcast -> React

- **Ingestion** (`stream_to_db.py`) - subscribes to live quotes and trade streams. Runs inside the API process as a background task. The FastAPI lifespan builds the stream, schedules it on the event loop, and starts the writer. A producer/consumer queue separates the socket callbacks from database writes, with time-based batching to limit write frequency. After each flush, `writer_loop()` awaits `on_flush()`, which the lifespan wires to `ConnectionManager.broadcast`. The broadcast carries an "update" message telling connected clients to refetch `/api/quotes`. Because it fires after the commit, a refetch never races the write. It also means broadcast rate inherits flush rate rather than being executed independently.

- **Backfill** (`backfill_history.py`) - pulls two years of adjusted OHLCV bars (open, high, low, close, volume). This is idempotent, so re-running will not cause any issues. `stale_bar_refetch()` runs from the lifespan at startup and refetches when `MAX(date)` is null or > 2 days old. Wrapped in a `try/except` block so a failed refresh doesn't block boot.

- **Metrics** (`metrics.py`) - computes annualized return and volatility from the loaded bars. More metrics to come in the roadmap.

- **API** (`main.py`) - FastAPI serving `/api/symbols`, `/api/bars/{symbol}`, `/api/metrics`, and `/api/quotes`. The `/api` prefix is used because `/` is mounted to the built frontend via `StaticFiles`. `/ws` is the WebSocket endpoint. `/api/quotes` returns `age_seconds`, `is_stale` (60s), and `as_of` - age computed from `ingested_at`, not Alpaca's `ts`. Its lifespan owns process startup and shutdown by initializing the schema, launching ingestion and the writer, and closing the Alpaca connection. Flushes remaining writes on exit.

- **Frontend** (`frontend/`) - Built with React + Typescript, with a WS-driven refetch and exponential backoff (double at 1s, cap at a max of 30s). Also features a 30s liveness poll so ages keep climbing when no messages arrive, and a status banner covering disconnected/reconnecting with a market-closed heuristic at 300s.

## Setup

Requires Python 3.12 and Node 24+.

### Backend

From the repo root:

```
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create an Alpaca account and generate paper trading API keys. Then copy
`backend/.env.example` to `backend/.env` and fill in:

| Variable | Required | Purpose |
| --- | --- | --- |
| `ALPACA_KEY` | yes | Alpaca API key ID |
| `ALPACA_SECRET` | yes | Alpaca API secret |
| `STREAM_TYPE` | no | `stock` (default) or `crypto`. Selects both the stream client and the subscribed symbols. |
| `DB_PATH` | no | Absolute path to the SQLite file. Defaults to `backend/market_data.db`. |

Start the server from the repo root:

```
uvicorn backend.main:app --reload
```


The backend is a package, so it must be launched from the root — running
`uvicorn main:app` from inside `backend/` fails on the relative imports.

Startup initializes the schema, backfills daily bars if they are missing or
more than two days stale, opens the Alpaca stream, and starts the database
writer. The API is served at <http://localhost:8000>.

To backfill manually and print a per-symbol summary:

```
python -m backend.backfill_history
```

This is optional. Startup performs the same backfill when the bars table is
empty, but the summary is useful for confirming row counts and date ranges.

### Frontend

``` 
cd frontend
npm install
npm run dev
```

The dashboard is at <http://localhost:5173>. The Vite dev server proxies
`/api` and `/ws` to port 8000, so the frontend uses relative paths in both
development and production and needs no environment configuration.

## Deployment

Deployed on Railway as a single service from the `Dockerfile` at the repo root.

**Build.** A multi-stage build keeps the runtime image Python-only. The first
stage (`node:24-alpine`) installs frontend dependencies with `npm ci` and runs
`npm run build`. The second stage (`python:3.12.11-slim`) installs the backend
requirements, copies `backend/`, and copies the compiled bundle from the
builder into `frontend/dist`. At import time `main.py` mounts that directory at
`/` via `StaticFiles`, so one container serves both the API and the dashboard
from the same origin — which is also why the frontend needs no API base URL and
why CORS is not a factor in production.

**Start command.** `railway.json` sets the DOCKERFILE builder and deliberately
defines no `startCommand`; the Dockerfile's `CMD` owns process launch. That
`CMD` is in `sh -c` form so `${PORT:-8000}` is expanded by a shell. Railway
injects `PORT` at runtime, and exec-form `CMD` would pass the literal string
`${PORT:-8000}` straight to uvicorn, which fails in argument parsing several
layers away from the actual cause.

**Persistence.** SQLite needs a filesystem that survives redeploys, so a Railway
volume is mounted at `/data` and `DB_PATH` points at `/data/market_data.db`.
Without it the container's writable layer is discarded on every deploy and the
database is recreated empty.

**Required variables.**

| Variable | Value |
| --- | --- |
| `ALPACA_KEY` | Alpaca API key ID |
| `ALPACA_SECRET` | Alpaca API secret |
| `DB_PATH` | `/data/market_data.db` |
| `STREAM_TYPE` | `stock` or `crypto` (optional, defaults to `stock`) |

`PORT` is supplied by Railway and should not be set manually.

**Single instance by design.** This service cannot be scaled horizontally. Two
constraints enforce it independently: SQLite is a single-writer embedded
database on a volume that attaches to one container, and the Alpaca free tier
permits one concurrent market data stream connection per account. Migrating to
PostgreSQL would relax the first but not the second — a second replica would
still need ingestion separated from the API process.

## Data Notes

Quotes and trades come from Alpaca's IEX feed (Investors Exchange), not the consolidated SIP (Securities Information Processor) feed. The difference is important to understand. IEX only covers ~2.5% of total market volume, so the quoted spreads only reflect a single venue's book rather than the national best/bid offer. Less liquid tickers show noticeably higher and more variable spreads than a consolidated view would. For example, MSFT regularly quotes over a dollar wide at IEX rather than a few pennies across the full market. This is a tradeoff of the data source, not a pipeline problem. The alternative would be the SIP, covering all U.S. stock exchanges, but this requires a subscription.

Another thing worth noting is Alpaca's free-tier single-stream-connection limit. Only one market data stream connection is allowed, with the limit being tied to the account's data subscription rather than a key pair. Both dev and prod authenticate as the same account, so whichever connects second gets rejected with a connection-limit error. However, because it's the stream that's restricted, historical REST calls are unaffected. This allows the local version to get historical backfill, `/api/metrics`, `/api/bars`, and whichever quotes are locally available in SQLite. 

## Design Decisions

**Async-safe persistence.** Blocking database writes inside an async callback would stall the event loop and make it fall behind, which Alpaca detects and ultimately closes the WebSocket connection. The `on_quote` and `on_trade` callbacks therefore only enqueue, pushing each message into an `asyncio.Queue` and returning immediately. `writer_loop` then drains the queue, and writes in time-based batches. Because it yields on `await` rather than blocking, the event loop stays responsive to incoming messages while writes are in progress. Batching further reduces transaction cost by distributing it across many rows rather than paying it per message.

**Idempotent writes.** Both backfill and the live quote writer use `INSERT ... ON CONFLICT ...  DO UPDATE SET`, which allows them to safely re-run and correct previously stored values. `DO UPDATE` rather than `DO NOTHING` is used because adjusted prices are not immutable. After a stock split, historical prices are restated, and `DO NOTHING` would leave pre-adjusted values and create a noticeable break in the chart. The trades table is the opposite, because its rows are completed events. Verified by running `backfill_history.py` twice and confirming identical rows with `inspect_db.py`.

**Bars over ticks.** Two years of bars across four symbols is ~2000 rows. If tick-level data was used instead, it would be in the millions. This decision was made more in mind of the scope of the project, not best practice. SQLite could store them, but it would have a hindrance on performance and add unnecessary bloat that isn't used. Bars are of the right granularity for annualized return and volatility, but if this project were ever expanded to include spread analysis, the switch would have to be made.

**Data quality guards.** When testing `stream_to_db.py`, some quotes arrived with a zero or missing price on one side. Alpaca sends one-sided updates, with some messages carrying a new bid with an empty ask price. Writing this data in would override a valid ask, leading to a very wide spread. This was fixed by adding `CHECK` constraints to the `latest_quotes` table and a guard in the `on_quote` callback. `bid_price` and `ask_price` must be `> 0` because a zero ask/bid price is meaningless. On the contrary, a zero size could be legitimate for `ask_size` and `bid_size` due to resting quantity of zero at that price, so they were checked to be `>= 0`. Surprisingly, this had less impact on the spread than expected. It turned out the remaining spreads were real, caused by IEX only covering a small portion of the total market.

## Roadmap

- ~~Websocket push to replace frontend polling~~
- Gap detection on reconnect
- Migration to PostgreSQL
- ~~Deployment on Railway~~
- User-interactive watchlist
- More metrics

