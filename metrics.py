import pandas as pd
import sqlite3

TRADING_DAYS = 252

def load_bars(db_path, symbols=None):
    """Load daily bars into a data frame index by (symbol, date)"""

    conn = sqlite3.connect(db_path)
    query = "SELECT symbol, date, close FROM daily_bars"
    params = ()

    if symbols:
        placeholders = ",".join("?" * len(symbols))
        query += f" WHERE symbol IN ({placeholders})"
        params = tuple(symbols)
    query += " ORDER BY symbol, date"

    df = pd.read_sql_query(query, conn, params=params, parse_dates=["date"])
    conn.close()
    return df

def daily_returns(df):
    """Add a daily_return column, computed per symbol"""
    df = df.copy()
    df["daily_return"] = df.groupby("symbol")["close"].pct_change() 
    return df 

def annualized_volatility(df):
    """Annualized standard deviation of daily_returns, per symbol"""
    return (df.groupby("symbol")["daily_return"].std(ddof=1) * (TRADING_DAYS ** 0.5)) # ddof is for sample std, not population

def annualized_return(df):
    """Compund annual growth rate from first and last close, per symbol"""
    out = {}
    for symbol, g in df.groupby("symbol"):
        years = len(g) / TRADING_DAYS
        out[symbol] = (g["close"].iloc[-1] / g["close"].iloc[0]) ** (1 / years) - 1

    return pd.Series(out)

