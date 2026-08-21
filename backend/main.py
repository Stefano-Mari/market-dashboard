import sqlite3
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from .metrics import daily_returns, load_bars, annualized_return, annualized_volatility
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from .stream_to_db import init_db, writer_loop, build_stream
from . import stream_to_db
import asyncio
from pathlib import Path


STALE_AFTER_SECONDS = 60
DB_PATH = Path(__file__).parent / "market_data.db"

class ConnectionManager:
    def __init__(self):
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.connections.discard(websocket)

    async def broadcast(self):
        dead = []
        for websocket in self.connections.copy():
            try:
                await websocket.send_text("update")
            except Exception:
                dead.append(websocket)

        for websocket in dead:
            self.disconnect(websocket)

manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stream_to_db.on_flush = manager.broadcast
    write_task = asyncio.create_task(writer_loop())
    stream = build_stream()
    stream_task = asyncio.create_task(stream._run_forever())
    try:
        yield 
    finally:
        await stream.stop_ws()
        stream_task.cancel()
        write_task.cancel()
        await asyncio.gather(stream_task, write_task, return_exceptions=True)

app = FastAPI(title="Market Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/symbols")
def get_symbols():
    """List all present symbols in the database."""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """SELECT DISTINCT symbol FROM daily_bars ORDER BY symbol"""
        ).fetchall()
    finally:
        conn.close()

    return {"symbols": [r[0] for r in rows]}

@app.get("/bars/{symbol}")
def get_bars(symbol: str, limit: int = 100):
    """Return the most recent daily OHLCV bars for a symbol, newest first."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
                SELECT date, open, high, low, close, volume
                FROM daily_bars WHERE symbol = ?
                ORDER BY date DESC
                LIMIT ?
                """, (symbol.upper(), limit)).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"No data for symbol {symbol.upper()}")
        
    finally:
        conn.close()

    return {
        "symbol": symbol.upper(),
        "count": len(rows),
        "bars": [dict(r) for r in rows],
    }

@app.get("/metrics")
def get_metrics():
    """Return CAGR and annualized volatility for every symbol."""
    df = daily_returns(load_bars(DB_PATH))
    vol = annualized_volatility(df)
    ret = annualized_return(df)
    return {
        "metrics":[
            {
                "symbol": sym,
                "annualized_return": round(float(ret[sym]), 4),
                "annualized_volatility": round(float(vol[sym]), 4),
            }
            for sym in sorted(vol.index)
        ]
    }

@app.get("/quotes")
def get_quotes():
    """Return the latest bid/ask per symbol, with a staleness flag."""
    symbols = stream_to_db.get_symbols()
    placeholders = ",".join("?" * len(symbols))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # injection is avoided here because SQLite parses the query structure first and THEN binds the values seperately
        rows = conn.execute(f"SELECT * FROM latest_quotes WHERE symbol IN ({placeholders}) ORDER BY symbol", symbols).fetchall()

    finally:
        conn.close()

    now = datetime.now(timezone.utc)
    quotes = []

    for r in rows:
        age = (now - datetime.fromisoformat(r["ingested_at"])).total_seconds()
        quotes.append({
            "symbol": r["symbol"],
            "bid_price": r["bid_price"],
            "ask_price": r["ask_price"],
            "spread": round(r["ask_price"] - r["bid_price"], 4),
            "ts": r["ts"],
            "age_seconds": round(age, 1),
            "is_stale": age > STALE_AFTER_SECONDS,
        }) 

    return {"quotes": quotes, "as_of": now.isoformat()}
