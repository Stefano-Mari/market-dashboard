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
    fetch(`${API_BASE}/symbols`)
      .then((res) => {
        if (!res.ok){
          throw new Error(`HTTP ${res.status}`);
        }
        return res.json();
      })
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
      fetch(`${API_BASE}/quotes`)
        .then((res) => {
          if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
          }
          return res.json();
      })
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

  if (loading) return <p>Loading…</p>;
  if (error && quotes.length === 0) return <p>Error: {error}</p>;

  return (
    <div>
      <h1>Market Dashboard</h1>
      {error && <p style={{ color: "#e57373"}}>Lost Connection - showing last known data</p>}
      <p>Tracking: {symbols.join(", ")}</p>
      <QuotesTable quotes={quotes} />
    </div>
  );
}

export default App;