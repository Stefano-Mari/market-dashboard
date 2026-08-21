import os
import Path
from dotenv import load_dotenv
from alpaca.data.live import StockDataStream

load_dotenv(Path(__file__).parent / ".env")

stream = StockDataStream(os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET"))

async def on_trade(trade):
    print(f"{trade.symbol:6} ${trade.price:>8.2f} size={trade.size}")

stream.subscribe_trades(on_trade, "AAPL", "TSLA", "SPY")
stream.run()