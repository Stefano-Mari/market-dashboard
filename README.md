# Real-Time Market Data Dashboard

A full-stack pipeline that streams live equity quotes and trades from Alpaca, persists them to a local database, and outputs them to a React Dashboard.

**Status:** in development. Core pipeline is functional; see roadmap for planned additions.

## Architecture

Alpaca Websocket -> asyncio queue -> batched SQLite writes -> FastAPI -> React

- **Ingestion** (`stream_to_db.py`) - subscribes to live quotes and trade streams. Runs inside the API process as a background task. The FastAPI lifespan builds the stream, schedules it on the event loop, and starts the writer. A producer/consumer queue separates the socket callbacks from database writes, with time-based batching to limit write frequency.

- **Backfill** (`backfill_history.py`) - pulls two years of adjusted OHLCV bars (open, high, low, close, volume). This is idempotent, so re-running will not cause any issues.

- **Metrics** (`metrics.py`) - computes annualized return and volatility from the loaded bars. More metrics to come in the roadmap.

- **API** (`main.py`) - FastAPI serving `/symbols`, `/bars/{symbol}`, `/metrics`, and `/quotes`. Its lifespan owns process startup and shutdown by initializing the schema, launching ingestion and the writer, and closing the Alpaca connection. Flushes remaining writes on exit.

- **Frontend** (`frontend/`) - Built with React + Typescript, with polling from `/quotes` every five seconds with a staleness indicator.

## Setup

### Backend

```
cd .\backend\
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

- Create an account on Alpaca's trading API and select paper trading.
- Copy `.env.example` to `.env` and fill in your Alpaca API key and secret.
- Run `python .\backfill_history.py` to retrieve historical backfill.

Then run the server:
``` 
uvicorn main:app --reload
```

This initializes the database schema, connects to Alpaca's live stream, and serves the API in a single process.

### Frontend

Exit backend directory using `cd ..`, and then:

``` 
cd .\frontend\
npm install
npm run dev
```

The dashboard is located at http://localhost:5173.

## Data Notes

Quotes and trades come from Alpaca's IEX feed (Investors Exchange), not the consolidated SIP (Securities Information Processor) feed. The difference is important to understand. IEX only covers ~2.5% of total market volume, so the quoted spreads only reflect a single venue's book rather than the national best/bid offer. Less liquid tickers show noticeably higher and more variable spreads than a consolidated view would. For example, MSFT regularly quotes over a dollar wide at IEX rather than a few pennies across the full market. This is a tradeoff of the data source, not a pipeline problem. The alternative would be the SIP, covering all U.S. stock exchanges, but this requires a subscription.

## Design Decisions

**Async-safe persistence.** Blocking database writes inside an async callback would stall the event loop and make it fall behind, which Alpaca detects and ultimately closes the WebSocket connection. The `on_quote` and `on_trade` callbacks therefore only enqueue, pushing each message into an `asyncio.Queue` and returning immediately. `writer_loop` then drains the queue, and writes in time-based batches. Because it yields on `await` rather than blocking, the event loop stays responsive to incoming messages while writes are in progress. Batching further reduces transaction cost by distributing it across many rows rather than paying it per message.

**Idempotent writes.** Both backfill and the live quote writer use `INSERT ... ON CONFLICT ...  DO UPDATE SET`, which allows them to safely re-run and correct previously stored values. `DO UPDATE` rather than `DO NOTHING` is used because adjusted prices are not immutable. After a stock split, historical prices are restated, and `DO NOTHING` would leave pre-adjusted values and create a noticeable break in the chart. The trades table is the opposite, because its rows are completed events. Verified by running `backfill_history.py` twice and confirming identical rows with `inspect_db.py`.

**Bars over ticks.** Two years of bars across four symbols is ~2000 rows. If tick-level data was used instead, it would be in the millions. This decision was made more in mind of the scope of the project, not best practice. SQLite could store them, but it would have a hindrance on performance and add unnecessary bloat that isn't used. Bars are of the right granularity for annualized return and volatility, but if this project were ever expanded to include spread analysis, the switch would have to be made.

**Data quality guards.** When testing `stream_to_db.py`, some quotes arrived with a zero or missing price on one side. Alpaca sends one-sided updates, with some messages carrying a new bid with an empty ask price. Writing this data in would override a valid ask, leading to a very wide spread. This was fixed by adding `CHECK` constraints to the `latest_quotes` table and a guard in the `on_quote` callback. `bid_price` and `ask_price` must be `> 0` because a zero ask/bid price is meaningless. On the contrary, a zero size could be legitimate for `ask_size` and `bid_size` due to resting quantity of zero at that price, so they were checked to be `>= 0`. Surprisingly, this had less impact on the spread than expected. It turned out the remaining spreads were real, caused by IEX only covering a small portion of the total market.

## Roadmap

- Websocket push to replace frontend polling
- Gap detection on reconnect
- Migration to PostgreSQL
- Deployment on Railway
- User-interactive watchlist
- More metrics

