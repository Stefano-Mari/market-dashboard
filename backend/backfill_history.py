import os
import Path
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment

DB_PATH = "market_data.db"
SYMBOLS = ["AAPL", "MSFT", "TSLA", "SPY"]
# 2 years = ~500 trading days per symbol
# This will be enough for volatility and correlation, but will be widened later
# note to self: Alpacas data starts in 2016
YEARS_BACK = 2 

load_dotenv(Path(__file__).parent / ".env")
API_KEY = os.getenv("ALPACA_KEY")
API_SECRET = os.getenv("ALPACA_SECRET")

def init_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS daily_bars (
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        volume INTEGER NOT NULL,
        PRIMARY KEY (symbol, date)
    );

    CREATE INDEX IF NOT EXISTS idx_bars_symbol_date
        ON daily_bars(symbol, date DESC);
    """)

    conn.commit()
    print(f"Database schema initialized at {DB_PATH}")

def fetch_bars():
    client = StockHistoricalDataClient(API_KEY, API_SECRET)
    # Due to Alpacas free API, we cannot fetch the most recent data.
    # Going back 20 minutes fixes this, and with little significance since these are daily bars anyway.
    end = datetime.now() - timedelta(minutes=20)
    start = end - timedelta(days=365 * YEARS_BACK)

    # Adjustment.ALL includes split and dividend corrections. 
    # Without it, a stock split will show up as an overnight price collapse, making every return calculation spanning that date wrong
    request = StockBarsRequest(symbol_or_symbols=SYMBOLS, timeframe=TimeFrame.Day, start=start, end=end, adjustment=Adjustment.ALL)
    print(f"Fetching {', '.join(SYMBOLS)} from {start.date()} to {end.date()} ...")
    barset = client.get_stock_bars(request)
    print("Fetch Complete")
    return barset

def to_rows(barset):
    # barset -> list of tuples matching the daily_bars column order
    rows = []
    for symbol, bars in barset.data.items():
        for b in bars:
            rows.append((
                symbol,
                # Alpaca stamps daily bars at market open in UTC, which falls on the same calendar day as the US session.
                # So, were safe to drop time here
                b.timestamp.date().isoformat(), 
                float(b.open), 
                float(b.high), 
                float(b.low), 
                float(b.close), 
                int(b.volume)
            ))
    return rows

def upsert_bars(conn, rows):
    # DO UPDATE rather than DO NOTHING because adjusted prices are not immutable.
    # DO NOTHING would silently preserve stale pre-split values and leave a break in the chart.
    # (Contrast with the trades table, where each row is a completed event that can never be restated. DO NOTHING is correct there)
    conn.executemany("""
        INSERT INTO daily_bars (symbol, date, open, high, low, close, volume)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, date) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume
    """, rows)
    conn.commit()

    # This counts rows SENT, not rows changed.
    # On a re-run it will report the full batch even though every row was an update
    print(f"Wrote {len(rows)} bars")

def summarize(conn):
    conn.row_factory = sqlite3.Row
    print(f"\n{'SYMBOL':<8}{'BARS':>7}{'FIRST':>14}{'LAST':>14}{'LAST CLOSE':>13}")
    print("-" * 56)

    # ~250 bars per year per symbol, with the exclusion of holidays and weekends
    # Anything different from other symbols signals a fetch problem
    for r in conn.execute("""
        SELECT symbol,
            COUNT(*) AS n,
            MIN(date) AS first_date,
            MAX(date) AS last_date
        FROM daily_bars
        GROUP BY symbol
        ORDER BY symbol
    """):
        close = conn.execute(
            "SELECT close FROM daily_bars WHERE symbol = ? AND date = ?",
            (r["symbol"], r["last_date"])).fetchone()["close"]
        
        print(f"{r['symbol']:<8}{r['n']:>7}{r['first_date']:>14}{r['last_date']:>14}{close:>13,.2f}")

    # Check for corrupt data. A zero or null close would break every downstream return calculation via division by zero.
    bad = conn.execute(
        "SELECT COUNT(*) FROM daily_bars WHERE close IS NULL OR close <= 0"
    ).fetchone()[0]

    print(f"\nSuspect rows (null/zero close): {bad}")

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    init_schema(conn)
    barset = fetch_bars()
    rows = to_rows(barset)
    upsert_bars(conn, rows)
    summarize(conn)
    conn.close()