import { useState, useEffect } from "react";
import QuotesTable from "./QuotesTable";
import type { Quote } from "./QuotesTable";

const API_BASE = "http://localhost:8000";

function App() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/symbols`).then((r) => r.json()),
      fetch(`${API_BASE}/quotes`).then((r) => r.json()),
    ])
      .then(([symbolsData, quotesData]) => {
        setSymbols(symbolsData.symbols);
        setQuotes(quotesData.quotes);
        setLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  }, []);

  if (loading) return <p>Loading…</p>;
  if (error) return <p>Error: {error}</p>;

  return (
    <div>
      <h1>Market Dashboard</h1>
      <p>Tracking: {symbols.join(", ")}</p>
      <QuotesTable quotes={quotes} />
    </div>
  );
}

export default App;