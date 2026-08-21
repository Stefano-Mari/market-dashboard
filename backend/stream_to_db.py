import asyncio
import os
import sqlite3
import time
from dotenv import load_dotenv
from alpaca.data.live import StockDataStream, CryptoDataStream
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "market_data.db"
FLUSH_SECONDS = 2
BATCH_SIZE = 100
on_flush = None

load_dotenv(Path(__file__).parent / ".env")
# STREAM_TYPE is below load_dotenv because it will silently read the wrong stream type if not.
# module-level config has a dependency on import order. It will fall back on the stock default rather than raise an error.
STREAM_TYPE = os.getenv("STREAM_TYPE") or "stock"

queue: asyncio.Queue = asyncio.Queue()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        price REAL NOT NULL,
        size REAL NOT NULL,
        ts TEXT NOT NULL,
        ingested_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts 
        ON trades(symbol, ts DESC);

    CREATE TABLE IF NOT EXISTS latest_quotes (
        symbol TEXT PRIMARY KEY,
        bid_price REAL NOT NULL CHECK (bid_price > 0),
        bid_size REAL NOT NULL CHECK (bid_size >= 0),
        ask_price REAL NOT NULL CHECK (ask_price > 0),
        ask_size REAL NOT NULL CHECK (ask_size >= 0),
        ts TEXT NOT NULL,
        ingested_at TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

def get_symbols():
        
    if STREAM_TYPE == "crypto":
        return ["BTC/USD", "ETH/USD"]
    
    return ["AAPL", "TSLA", "MSFT", "SPY"]
    

def build_stream():
    key, secret = os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET")
    symbols = get_symbols()

    stream = CryptoDataStream(key, secret) if STREAM_TYPE == "crypto" else StockDataStream(key, secret)
    
    print(f"Streaming {STREAM_TYPE}: {', '.join(symbols)}")
    stream.subscribe_trades(on_trade, *symbols)
    stream.subscribe_quotes(on_quote, *symbols)

    return stream

# function to flush trades and quotes to the database
def flush(conn, trades, quotes):
    if trades:
        conn.executemany(
            "INSERT INTO trades (symbol, price, size, ts, ingested_at) VALUES (?, ?, ?, ?, ?)", trades)
    if quotes:
        conn.executemany(
            """INSERT INTO latest_quotes (symbol, bid_price, bid_size, ask_price, ask_size, ts, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    bid_price=excluded.bid_price,
                    bid_size=excluded.bid_size,
                    ask_price=excluded.ask_price,
                    ask_size=excluded.ask_size,
                    ts=excluded.ts,
                    ingested_at=excluded.ingested_at""",
            list(quotes.values()),
        )
    conn.commit()
    if trades or quotes:
        print(f"flushed {len(trades)} trades, {len(quotes)} quotes to the database.")

# async function to continuously write trades and quotes to the database
async def writer_loop():
    conn = sqlite3.connect(DB_PATH)
    trades, quotes = [], {}
    last_flush = time.monotonic() # monotonic is used to avoid issues with system clock changes
    try:
        while True:
            try:
                kind, row = await asyncio.wait_for(queue.get(), timeout=FLUSH_SECONDS) # returns a tuple of (kind, row)
                if kind == "trade":
                    trades.append(row)
                else:
                    quotes[row[0]] = row  # this is a dict with symbol as key
            except asyncio.TimeoutError:
                pass # timeout, flush whatever we have

            now = time.monotonic()
            if (now - last_flush >= FLUSH_SECONDS) or (len(trades) >= BATCH_SIZE):
                if trades or quotes:
                    flush(conn, trades, quotes)
                    trades, quotes = [], {} # reset for next batch
                    last_flush = time.monotonic() # update the last flush time
                    if on_flush is not None:
                        await on_flush()

    except asyncio.CancelledError:
        if trades or quotes:
            flush(conn, trades, quotes)
        raise 

    finally:
        conn.close()

# async function to handle incoming trades and put them in the queue
# await is needed here because queue.put is an async function
async def on_trade(trade):
    ingested_at = datetime.now(timezone.utc).isoformat()
    await queue.put(("trade", (trade.symbol, float(trade.price), float(trade.size), trade.timestamp.isoformat(), ingested_at)))

async def on_quote(quote):
    if quote.bid_price <= 0 or quote.ask_price <= 0:
        return # skip malformed quotes
    ingested_at = datetime.now(timezone.utc).isoformat()
    
    await queue.put(("quote", (quote.symbol, float(quote.bid_price), float(quote.bid_size),
                                float(quote.ask_price), float(quote.ask_size), quote.timestamp.isoformat(), ingested_at)))
