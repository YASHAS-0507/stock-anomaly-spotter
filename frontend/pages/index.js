import { useState, useEffect, useMemo } from "react";
import { usePrediction } from "@/hooks/usePrediction";
import { formatPrice, formatPercent, formatTimestamp } from "@/utils/formatting";
import { getDominantClass, getAccuracyStatus, extractRiskPortfolio } from "@/utils/prediction";
import { getMarketStatus, getValidationStats, getCacheInfo } from "@/services/market";

// Components - Layout
import TopBar from "@/components/TopBar";
import TickerInput from "@/components/TickerInput";

// Components - Dashboard
import LivePriceChart from "@/components/dashboard/LivePriceChart";
import PredictionEngine from "@/components/dashboard/PredictionEngine";
import TradeSetup from "@/components/dashboard/TradeSetup";
import PortfolioCard from "@/components/dashboard/PortfolioCard";
import MarketHealthCard from "@/components/dashboard/MarketHealthCard";
import ModelDiagnosticsCard from "@/components/dashboard/ModelDiagnosticsCard";
import ExplainabilityCard from "@/components/dashboard/ExplainabilityCard";
import SystemHealthCard from "@/components/dashboard/SystemHealthCard";
import MarketDataDashboard from "@/components/dashboard/MarketDataDashboard";

export default function Home() {
  const [ticker, setTicker] = useState("RELIANCE.NS");
  const [period, setPeriod] = useState("1y");
  const [horizon, setHorizon] = useState("5");
  const [currentInterval, setCurrentInterval] = useState("1d");
  const [refreshKey, setRefreshKey] = useState(0);
  const [marketStatus, setMarketStatus] = useState(null);
  const [validationStats, setValidationStats] = useState(null);
  const [cacheInfo, setCacheInfo] = useState(null);

  const {
    analysis,
    prediction,
    chartTrend,
    loading,
    error,
    drag,
    setDrag,
    runAnalysis,
    handleUploadChart,
    handleLogout,
    clearError
  } = usePrediction();

  // Extract nested data safely
  const { risk, portfolio, explain, signal } = useMemo(() => 
    prediction ? extractRiskPortfolio(prediction) : {}, 
  [prediction]);

  // Derived prediction data
  const { dominant, probSideways, probSpikeUp, probSpikeDown } = useMemo(
    () => getDominantClass(prediction),
    [prediction]
  );

  const { beat: accBeat, tie: accTie, diff: accDiff } = useMemo(
    () => getAccuracyStatus(prediction),
    [prediction]
  );

  const marketStatusSafe = marketStatus ?? {
    exchange: "N/A",
    market_status: "N/A",
    feed_status: "N/A",
    latency_ms: "N/A",
    latest_candle: "N/A",
    data_quality: "N/A",
    current_time_ist: "N/A",
  };

  useEffect(() => {
    let cancelled = false;

    const loadMarketData = async () => {
      try {
        const [status, validation, cache] = await Promise.all([
          getMarketStatus(),
          getValidationStats(),
          getCacheInfo()
        ]);
        if (cancelled) return;
        setMarketStatus(status);
        setValidationStats(validation);
        setCacheInfo(cache);
      } catch (err) {
        if (!cancelled) {
          console.warn("[index] market data refresh failed", err);
        }
      }
    };

    loadMarketData();
    const timer = setInterval(loadMarketData, 10000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  // Handle analysis run
  const handleRun = () => {
    runAnalysis(ticker, period, horizon);
    setRefreshKey(k => k + 1);
  };

  // Auto-refresh market data
  useEffect(() => {
    const timer = setInterval(() => {
      setRefreshKey(k => k + 1);
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="terminal-layout">
      {/* TOP HEADER */}
      <header className="terminal-header panel">
        <div className="header-left">
          <div className="brand">
            <div className="brand-dot" />
            <div>
              <div className="brand-name">Stock Anomaly Spotter</div>
              <div className="brand-tag">Institutional Trading Terminal</div>
            </div>
          </div>
          <div className="current-symbol">
            <span className="text-label">Current Symbol</span>
            <span className="text-title">{ticker}</span>
          </div>
        </div>

        <div className="header-center">
          <div className="market-status-indicator">
            <span className="text-label">Market Status</span>
            <div className="flex items-center gap-sm">
              <span className={`badge-dot status-${String(marketStatusSafe.market_status).toLowerCase()}`} />
              <span className="text-title signal-hold">{marketStatusSafe.market_status}</span>
            </div>
          </div>
        </div>

        <div className="header-right">
          <div className="flex items-center gap-md text-right">
            <div>
              <span className="text-label">Feed Status</span>
              <div className="flex items-center gap-sm justify-end">
                <span className={`badge-dot status-${String(marketStatusSafe.feed_status).toLowerCase()}`} />
                <span className="text-body signal-neutral">{marketStatusSafe.feed_status}</span>
              </div>
            </div>
            <div className="hidden md:block">
              <span className="text-label">Latency</span>
              <div className="flex items-center justify-end gap-sm">
                <span className="text-metric-sm font-mono">{marketStatusSafe.latency_ms}ms</span>
              </div>
            </div>
            <div>
              <span className="text-label">Current Time</span>
              <div className="flex items-center justify-end gap-sm">
                <span className="text-metric-sm font-mono" id="current-time">--:--:--</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* TICKER INPUT */}
      <TickerInput
        ticker={ticker}
        period={period}
        horizon={horizon}
        currentInterval={currentInterval}
        onTickerChange={e => setTicker(e.target.value.toUpperCase())}
        onPeriodChange={e => setPeriod(e.target.value)}
        onHorizonChange={e => setHorizon(e.target.value)}
        onIntervalChange={e => setCurrentInterval(e.target.value)}
        onRun={handleRun}
        loading={loading}
      />

      {error && (
        <div className="error-banner panel bg-sell" style={{ maxWidth: "1920px", margin: "0 auto var(--space-md)" }}>
          <div className="panel-content flex items-center justify-between">
            <span>⚠ {error}</span>
            <button className="btn btn-ghost btn-sm" onClick={clearError}>Dismiss</button>
          </div>
        </div>
      )}

      {/* MAIN GRID */}
      <div style={{ maxWidth: "1920px", margin: "0 auto", width: "100%" }}>
        <div className="terminal-main">
          {/* LEFT COLUMN - 70% */}
        
                  {/* 1. LIVE PRICE CHART */}
                  <LivePriceChart
                    analysis={analysis}
                    key="live-price-chart"
                    currentInterval={currentInterval}
                    onIntervalChange={setCurrentInterval}
                  />

                  {/* 2. PREDICTION ENGINE */}
                  <PredictionEngine
                    prediction={prediction}
                    dominant={dominant}
                    probSideways={probSideways}
                    probSpikeUp={probSpikeUp}
                    probSpikeDown={probSpikeDown}
                    accBeat={accBeat}
                    accTie={accTie}
                    accDiff={accDiff}
                    signal={signal}
                    key="prediction-engine"
                  />

                  {/* 3. TRADE SETUP */}
                  <TradeSetup
                    risk={risk}
                    portfolio={portfolio}
                    signal={signal}
                    key="trade-setup"
                  />
                </div>

                {/* RIGHT COLUMN - 30% */}
                <aside className="terminal-sidebar">
                  {/* PORTFOLIO CARD */}
                  <PortfolioCard
                    portfolio={portfolio}
                    risk={risk}
                    key="portfolio-card"
                  />

                  {/* MARKET HEALTH CARD */}
                  <MarketHealthCard
                    marketStatus={marketStatus}
                    currentInterval={currentInterval}
                    key="market-health-card"
                  />

                  {/* MODEL DIAGNOSTICS CARD */}
                  <ModelDiagnosticsCard
                    prediction={prediction}
                    dominant={dominant}
                    accBeat={accBeat}
                    accTie={accTie}
                    accDiff={accDiff}
                    key="model-diagnostics-card"
                  />

                  {/* EXPLAINABILITY CARD */}
                  <ExplainabilityCard
                    explain={explain}
                    key="explainability-card"
                  />

                  {/* MARKET DATA DASHBOARD */}
                  <MarketDataDashboard
                    key="market-data-dashboard"
                    status={marketStatus}
                    validationStats={validationStats}
                    cacheInfo={cacheInfo}
                    loading={!marketStatus && !validationStats && !cacheInfo}
                    currentInterval={currentInterval}
                    onIntervalChange={setCurrentInterval}
                  />
                </aside>
              </div>

              {/* BOTTOM SECTION - SYSTEM HEALTH */}
              <div style={{ maxWidth: "1920px", margin: "0 auto", width: "100%" }}>
                <div className="terminal-bottom">
                  <SystemHealthCard
                    validationStats={validationStats}
                    cacheInfo={cacheInfo}
                    key="system-health-card"
                  />
                </div>
              </div>
    </div>
  );
}
