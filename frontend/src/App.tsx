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
    fetch(`${API_BASE}/symbols`).then((r) => r.json())
      .then((symbolsData) => {
        setSymbols(symbolsData.symbols);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    const pollStatus = () => {
      fetch(`${API_BASE}/quotes`).then((r) => r.json())
        .then((quotesData) => {
          setQuotes(quotesData.quotes);
          setError(null);
          setLoading(false);
        })
        .catch((err) => {
          setError(String(err));
          setLoading(false);
        });
    }
    pollStatus();
    const interval = setInterval(pollStatus, 5000);

    return () => clearInterval(interval);
  }, []);

  if (error) return <p>Error: {error}</p>;
  if (loading) return <p>Loading…</p>;

  return (
    <div>
      <h1>Market Dashboard</h1>
      <p>Tracking: {symbols.join(", ")}</p>
      <QuotesTable quotes={quotes} />
    </div>
  );
}

export default App;