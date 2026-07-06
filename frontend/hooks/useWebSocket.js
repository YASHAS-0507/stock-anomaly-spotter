import { useState, useEffect, useRef, useCallback } from "react";

const WS_BASE = (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000")
  .replace(/^http/, "ws");

const MAX_BACKOFF_MS = 30_000;

export function useWebSocket() {
  const [connected, setConnected]           = useState(false);
  const [latency, setLatency]               = useState(null);
  const [lastMessage, setLastMessage]       = useState(null);
  const [marketStatus, setMarketStatus]     = useState("CLOSED");
  const [tickerPrices, setTickerPrices]     = useState({});
  const [wsSchedulerStatus, setWsSchedulerStatus] = useState(null);

  const wsRef         = useRef(null);
  const backoffRef    = useRef(1000);
  const retryTimerRef = useRef(null);
  const mountedRef    = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    try {
      const ws = new WebSocket(`${WS_BASE}/ws`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) { ws.close(); return; }
        setConnected(true);
        backoffRef.current = 1000; // reset backoff on successful connect
        const sentAt = Date.now();
        // measure round-trip on first open
        setLatency(Date.now() - sentAt);
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const msg = JSON.parse(event.data);
          const receivedAt = Date.now();

          if (msg.type === "ping") {
            setLatency(receivedAt - (msg.timestamp || receivedAt));
            return;
          }

          if (msg.type === "market_status") {
            setLatency(receivedAt - (msg.timestamp || receivedAt));
            setMarketStatus(msg.data?.market_status ?? "CLOSED");
          }

          // Phase 3: live tick prices from Angel One feed
          if (msg.type === "live_tick") {
            const { ticker, price } = msg.data || {};
            if (ticker && price != null) {
              setTickerPrices((prev) => ({ ...prev, [ticker]: price }));
            }
          }

          // Phase 3: scheduler summary broadcast (every 10s)
          if (msg.type === "scheduler_status") {
            setWsSchedulerStatus(msg.data || null);
          }

          // Phase 3: position/trade events — surface via lastMessage so
          // consumers can trigger a REST refresh (position_update, trade_closed)
          setLastMessage(msg);
        } catch (_) {}
      };

      ws.onerror = () => {
        // onclose will fire after onerror; handle reconnect there
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setConnected(false);
        wsRef.current = null;

        // Exponential backoff reconnect
        const delay = Math.min(backoffRef.current, MAX_BACKOFF_MS);
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
        retryTimerRef.current = setTimeout(connect, delay);
      };
    } catch (_) {
      // WebSocket constructor can throw if URL is invalid
      const delay = Math.min(backoffRef.current, MAX_BACKOFF_MS);
      backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
      retryTimerRef.current = setTimeout(connect, delay);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      clearTimeout(retryTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on intentional close
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return {
    connected,
    latency,
    lastMessage,
    marketStatus,
    tickerPrices,
    wsSchedulerStatus,
  };
}
