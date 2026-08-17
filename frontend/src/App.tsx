import { useState, useEffect } from "react";
import QuotesTable from "./QuotesTable";
import type { Quote } from "./QuotesTable";

const API_BASE = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws";
type ConnectionStatus = "connected" | "disconnected" | "reconnecting";

function App() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");

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
    let websocket: WebSocket | null = null;
    let retryClock: ReturnType<typeof setTimeout>;
    let attempts: number = 0;
    let cancelled: boolean = false;

    const fetchQuotes = () => {
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
    fetchQuotes();

    const connect = () => {
      websocket = new WebSocket(WS_URL);

      websocket.onopen = () => {
        fetchQuotes();
        setStatus("connected");
        attempts = 0;
      };

      websocket.onmessage = () => fetchQuotes();

      websocket.onclose = () => {
        if (cancelled) return;
        setStatus("reconnecting");
        const delay = Math.min(1000 * 2 ** attempts, 30000);
        attempts++;
        retryClock = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryClock);
      websocket?.close();
    }
  }, []);

  if (loading) return <p>Loading…</p>;
  if (error && quotes.length === 0) return <p>Error: {error}</p>;

  return (
    <div>
      <h1>Market Dashboard</h1>
      {status !== "connected" && (
        <p style={{ color: "#e57373"}}>
          {status === "reconnecting" ? "Reconnecting..." : "Disconnected"} - showing last known data
        </p>
      )}
      <p>Tracking: {symbols.join(", ")}</p>
      <QuotesTable quotes={quotes} />
    </div>
  );
}

export default App;