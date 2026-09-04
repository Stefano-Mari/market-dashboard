import { useState, useEffect } from "react";
import QuotesTable from "./QuotesTable";
import type { Quote } from "./QuotesTable";
import type { Metric } from "./MetricsTable";
import MetricsTable from "./MetricsTable";

export type ConnectionStatus = "connected" | "disconnected" | "reconnecting";
const MARKET_CLOSED_THRESHOLD = 300 // threshold for determining if the market is closed
const AGE_REFRESH_INTERVAL = 30000

function App() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const isClosed: boolean = quotes.length > 0 && quotes.every((q) => q.age_seconds > MARKET_CLOSED_THRESHOLD)

  useEffect(() => {
    fetch("/api/symbols")
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
    fetch("/api/metrics")
      .then((res) => {
        if (!res.ok){
          throw new Error(`HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((metricsData) => {
        setMetrics(metricsData.metrics);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    let websocket: WebSocket | null = null;
    let retryClock: ReturnType<typeof setTimeout>;
    let refreshClock: ReturnType<typeof setInterval>;
    let attempts: number = 0;
    let cancelled: boolean = false;

    const fetchQuotes = () => {
      fetch("/api/quotes")
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
      const scheme = (window.location.protocol === "https:" ? "wss:" : "ws:");
      const wsURL = `${scheme}//${window.location.host}/ws`;
      websocket = new WebSocket(wsURL);

      websocket.onopen = () => {
        fetchQuotes();
        setStatus("connected");
        attempts = 0;
      };

      websocket.onmessage = () => fetchQuotes();

      websocket.onerror = () => {
        console.log(`WS error on ${wsURL}`);
      }

      websocket.onclose = (event: CloseEvent) => {
        if (cancelled) return;
        setStatus("reconnecting");
        const delay = Math.min(1000 * 2 ** attempts, 30000);
        attempts++;
        retryClock = setTimeout(connect, delay);
        console.log(`WS closed, retry #${attempts} in ${delay}ms`);
        console.log(`${event.code} - ${event.reason}`);
      };
    };

    refreshClock = setInterval(fetchQuotes, AGE_REFRESH_INTERVAL);
    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryClock);
      clearInterval(refreshClock);
      websocket?.close();
    }
  }, []);

  if (loading) return <p>Loading…</p>;
  if (error && quotes.length === 0) return <p>Error: {error}</p>;

  let statusMessage: string | null = null;

  if (status !== "connected") {
    statusMessage = `${status === "reconnecting" ? "Reconnecting..." : "Disconnected"} - showing last known data`; 
  }
  else if (isClosed) {
    statusMessage = "No recent data - markets may be closed";
  }

  return (
    <div>
      <h1>Market Dashboard</h1>
      {statusMessage && 
        <p style={{ color: "#e57373"}}>
          {statusMessage}
        </p>
      }
      <p>Tracking: {symbols.join(", ")}</p>
      <h2>Quotes</h2>
      <QuotesTable quotes={quotes} />
      <h2>Metrics</h2>
      <MetricsTable metrics={metrics} />
    </div>
  );
}

export default App;