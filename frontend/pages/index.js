import { useState, useEffect } from "react";
import { usePrediction } from "../hooks/usePrediction";
import TopBar               from "../components/TopBar";
import TickerInput          from "../components/TickerInput";
import LivePriceChart       from "../components/LivePriceChart";
import PredictionEngine     from "../components/PredictionEngine";
import TradeSetup           from "../components/TradeSetup";
import PortfolioCard        from "../components/PortfolioCard";
import MarketHealthCard     from "../components/MarketHealthCard";
import ModelDiagnosticsCard from "../components/ModelDiagnosticsCard";
import ExplainabilityCard   from "../components/ExplainabilityCard";
import ExecutionQueueCard   from "../components/ExecutionQueueCard";
import MarketDataDashboard  from "../components/MarketDataDashboard";
import SystemHealthCard     from "../components/SystemHealthCard";
import LiveTickerStrip      from "@/components/intraday/LiveTickerStrip";
import ActivePositions      from "@/components/intraday/ActivePositions";
import TodayStats           from "@/components/intraday/TodayStats";
import AutoTradeLog         from "@/components/intraday/AutoTradeLog";
import ScannerCard          from "@/components/intraday/ScannerCard";
import RegimeMatrix         from "@/components/intraday/RegimeMatrix";
import SchedulerControls    from "@/components/intraday/SchedulerControls";
import CandlestickChart     from "@/components/intraday/CandlestickChart";
import AnalyticsDashboard   from "../components/analytics/AnalyticsDashboard";
import {
  fetchSchedulerStatus,
  fetchLivePositions,
  fetchTodayTrades,
  fetchWatchlist,
  postSchedulerControl,
  fetchCandles,
  fetchAnalytics,
} from "../services/api";

export default function Home() {
  const {
    ticker, setTicker,
    period, setPeriod,
    horizon, setHorizon,
    chartInterval, setChartInterval,
    analysis, prediction, decision,
    loading, error, latency,
    runAnalysis,
  } = usePrediction();

  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [livePositions, setLivePositions]     = useState([]);
  const [todayTrades, setTodayTrades]         = useState([]);
  const [watchlist, setWatchlist]             = useState([]);
  const [liveLoading, setLiveLoading]         = useState(false);
  const [candleData, setCandleData]           = useState([]);
  const [candleInterval, setCandleInterval]   = useState("5min");
  const [candleLoading, setCandleLoading]     = useState(false);
  const [analyticsData, setAnalyticsData]     = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [activeTab, setActiveTab]             = useState("trading"); // "trading" | "analytics"

  async function fetchLiveData() {
    try {
      setLiveLoading(true);
      const [status, positions, trades, wl] = await Promise.all([
        fetchSchedulerStatus(),
        fetchLivePositions(),
        fetchTodayTrades(),
        fetchWatchlist(),
      ]);
      setSchedulerStatus(status);
      setLivePositions(positions.open_positions || []);
      setTodayTrades(trades || []);
      setWatchlist(wl.watchlist || []);
    } catch (e) {
      console.error("Live data fetch failed:", e);
    } finally {
      setLiveLoading(false);
    }
  }

  async function fetchCandleData(t, iv) {
    const candleTicker = t || ticker;
    if (!candleTicker) return;
    try {
      setCandleLoading(true);
      const data = await fetchCandles(candleTicker, iv || candleInterval);
      setCandleData(data.candles || []);
    } catch (e) {
      console.error("Candle fetch failed:", e);
    } finally {
      setCandleLoading(false);
    }
  }

  useEffect(() => { fetchLiveData(); }, []);

  useEffect(() => {
    const interval = setInterval(fetchLiveData, 30000);
    return () => clearInterval(interval);
  }, []);

  async function loadAnalytics() {
    try {
      setAnalyticsLoading(true);
      const data = await fetchAnalytics();
      setAnalyticsData(data);
    } catch (e) {
      console.error("Analytics fetch failed:", e);
    } finally {
      setAnalyticsLoading(false);
    }
  }

  useEffect(() => {
    loadAnalytics();
    const id = setInterval(loadAnalytics, 300000); // refresh every 5 minutes
    return () => clearInterval(id);
  }, []);

  // Refresh candles when analysis ticker changes or scheduler is running
  useEffect(() => {
    if (ticker && schedulerStatus?.scheduler_running) {
      fetchCandleData(ticker, candleInterval);
      const id = setInterval(() => fetchCandleData(ticker, candleInterval), 60000);
      return () => clearInterval(id);
    }
  }, [ticker, candleInterval, schedulerStatus?.scheduler_running]);

  return (
    <div className="page">
      <TopBar analysis={analysis} latency={latency} />

      {/* Live ticker strip — always visible at top */}
      <LiveTickerStrip
        prices={schedulerStatus?.broker?.open_positions || []}
        watchlist={watchlist}
        loading={liveLoading}
      />

      <TickerInput
        ticker={ticker}         setTicker={setTicker}
        period={period}         setPeriod={setPeriod}
        horizon={horizon}       setHorizon={setHorizon}
        chartInterval={chartInterval} setChartInterval={setChartInterval}
        onRun={runAnalysis}     loading={loading}
      />

      {error && <div className="error-bar">⚠ {error}</div>}

      {analysis && (
        <div className="results">

          {/* Row 1: Live chart (wider) + Prediction engine (sidebar) */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 340px",
            gap: 16,
            marginBottom: 16,
            alignItems: "start",
          }}>
            {schedulerStatus?.scheduler_running ? (
              <CandlestickChart
                candles={candleData}
                ticker={ticker}
                interval={candleInterval}
                anomalies={analysis?.anomaly_dates || []}
                loading={candleLoading}
                onIntervalChange={(iv) => {
                  setCandleInterval(iv);
                  fetchCandleData(ticker, iv);
                }}
              />
            ) : (
              <LivePriceChart analysis={analysis} />
            )}
            <PredictionEngine prediction={prediction} decision={decision} />
          </div>

          {/* Row 2: Trade Setup · Portfolio · Market Health */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 16,
            marginBottom: 16,
            alignItems: "start",
          }}>
            <TradeSetup     prediction={prediction} decision={decision} />
            <PortfolioCard />
            <MarketHealthCard analysis={analysis}   />
          </div>

          {/* Row 3: Model Diagnostics · Explainability */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 16,
            marginBottom: 16,
            alignItems: "start",
          }}>
            <ModelDiagnosticsCard prediction={prediction} />
            <ExplainabilityCard   prediction={prediction} />
          </div>

          {/* Row 4: Execution Queue */}
          <div style={{ marginBottom: 16 }}>
            <ExecutionQueueCard decision={decision} loading={loading} />
          </div>

          {/* Row 5: Market Data Dashboard · System Health */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 16,
            marginBottom: 16,
            alignItems: "start",
          }}>
            <MarketDataDashboard analysis={analysis} prediction={prediction} />
            <SystemHealthCard    latency={latency} />
          </div>

        </div>
      )}

      {/* ── Tab selector ── */}
      <div style={{ display: "flex", gap: 8, marginTop: 24, marginBottom: 16 }}>
        {[
          { key: "trading",   label: "Trading" },
          { key: "analytics", label: "Analytics" },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              fontFamily: "var(--mono)", fontSize: 11, fontWeight: 600,
              padding: "7px 18px", borderRadius: 7, cursor: "pointer",
              border: "1px solid",
              borderColor: activeTab === key ? "var(--cyan)" : "var(--border)",
              background: activeTab === key ? "rgba(0,208,255,0.1)" : "var(--surface)",
              color: activeTab === key ? "var(--cyan)" : "var(--text-3)",
              letterSpacing: "0.06em",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Analytics tab ── */}
      {activeTab === "analytics" && (
        <AnalyticsDashboard data={analyticsData} loading={analyticsLoading} />
      )}

      {/* ── Phase 3: Intraday Autonomous Trading Section ── */}
      {activeTab === "trading" && <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 340px",
        gap: 16,
        alignItems: "start",
      }}>
        {/* Left column */}
        <div>
          <SchedulerControls
            status={schedulerStatus}
            onAction={async (action) => {
              await postSchedulerControl(action);
              await fetchLiveData();
            }}
            loading={liveLoading}
          />
          <TodayStats
            portfolio={schedulerStatus?.broker}
            loading={liveLoading}
          />
          <AutoTradeLog
            trades={todayTrades}
            loading={liveLoading}
          />
        </div>

        {/* Right column */}
        <div>
          <ActivePositions
            positions={livePositions}
            currentPrices={{}}
            loading={liveLoading}
          />
          <ScannerCard
            watchlist={watchlist}
            intelligence={schedulerStatus?.intelligence || {}}
            loading={liveLoading}
          />
          <RegimeMatrix
            watchlist={watchlist}
            regimes={{}}
            loading={liveLoading}
          />
        </div>
      </div>}
    </div>
  );
}
