import sqlite3

conn = sqlite3.connect('market_data.db')
conn.row_factory = sqlite3.Row

print("\n=== Latest Quotes ===")
for row in conn.execute('SELECT * FROM latest_quotes'):
    print(f"{row['symbol']:10} bid={row['bid_price']:^10.2f} ask={row['ask_price']:^10.2f} spread={row['ask_price'] - row['bid_price']:^10.2f}")

print("\n=== Trade Count by Symbol ===")
for row in conn.execute('SELECT symbol, COUNT(*) n FROM trades GROUP BY symbol'):
    print(f"{row['symbol']:10} {row['n']} trades")

print("\n=== 5 Most Recent Trades ===")
for row in conn.execute('SELECT * FROM trades ORDER BY ts DESC LIMIT 5'):
    print(f"{row['ts']}  {row['symbol']:10} ${row['price']:^10.2f}  size={row['size']:^10}")

conn.close()

# note to self: SPY is so low because it was removed from the stream after a few seconds, so only a few trades were recorded.