import asyncio
import os
import sqlite3
import time
from dotenv import load_dotenv
from alpaca.data.live import StockDataStream, CryptoDataStream

DB_PATH = "market_data.db"
FLUSH_SECONDS = 2
BATCH_SIZE = 100

load_dotenv()

queue: asyncio.Queue = asyncio.Queue()
_writer_task = None

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        price REAL NOT NULL,
        size REAL NOT NULL,
        ts TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts 
        ON trades(symbol, ts DESC);

    CREATE TABLE IF NOT EXISTS latest_quotes (
        symbol TEXT PRIMARY KEY,
        bid_price REAL NOT NULL CHECK (bid_price > 0),
        bid_size REAL NOT NULL CHECK (bid_size >= 0),
        ask_price REAL NOT NULL CHECK (ask_price > 0),
        ask_size REAL NOT NULL CHECK (ask_size >= 0),
        ts TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

def build_stream():
    key, secret = os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET")
    stream_type = os.getenv("STREAM_TYPE", "stock").lower()
    
    if stream_type == "crypto":
        stream = CryptoDataStream(key, secret)
        symbols = ["BTC/USD", "ETH/USD"]
    else:
        stream = StockDataStream(key, secret)
        symbols = ["AAPL", "TSLA", "MSFT", "SPY"]
    
    print(f"Streaming {stream_type}: {', '.join(symbols)}")
    stream.subscribe_trades(on_trade, *symbols)
    stream.subscribe_quotes(on_quote, *symbols)

    return stream

# function to flush trades and quotes to the database
def flush(conn, trades, quotes):
    if trades:
        conn.executemany(
            "INSERT INTO trades (symbol, price, size, ts) VALUES (?, ?, ?, ?)", trades)
    if quotes:
        conn.executemany(
            """INSERT INTO latest_quotes (symbol, bid_price, bid_size, ask_price, ask_size, ts)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    bid_price=excluded.bid_price,
                    bid_size=excluded.bid_size,
                    ask_price=excluded.ask_price,
                    ask_size=excluded.ask_size,
                    ts=excluded.ts""",
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

# function to start the writer loop if it's not already running
def start_writer():
    global _writer_task
    if _writer_task is None:
        _writer_task = asyncio.create_task(writer_loop())

# async function to handle incoming trades and put them in the queue
# await is needed here because queue.put is an async function
async def on_trade(trade):
    start_writer()
    await queue.put(("trade", (trade.symbol, float(trade.price), float(trade.size), trade.timestamp.isoformat())))

async def on_quote(quote):
    start_writer()
    if quote.bid_price <= 0 or quote.ask_price <= 0:
        return # skip malformed quotes
    
    await queue.put(("quote", (quote.symbol, float(quote.bid_price), float(quote.bid_size),
                                float(quote.ask_price), float(quote.ask_size), quote.timestamp.isoformat())))

if __name__ == "__main__":
    init_db()
    stream = build_stream()
    stream.run()
