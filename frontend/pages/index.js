import { useState, useEffect, useMemo } from "react";
import { usePrediction } from "@/hooks/usePrediction";
import { getDominantClass, getAccuracyStatus, extractRiskPortfolio } from "@/utils/prediction";
import { getMarketStatus, getValidationStats, getCacheInfo } from "@/services/market";

// Layout components
import TopBar from "@/components/TopBar";
import TickerInput from "@/components/TickerInput";

// Dashboard components
import LivePriceChart       from "@/components/dashboard/LivePriceChart";
import PredictionEngine     from "@/components/dashboard/PredictionEngine";
import TradeSetup           from "@/components/dashboard/TradeSetup";
import PortfolioCard        from "@/components/dashboard/PortfolioCard";
import MarketHealthCard     from "@/components/dashboard/MarketHealthCard";
import ModelDiagnosticsCard from "@/components/dashboard/ModelDiagnosticsCard";
import ExplainabilityCard   from "@/components/dashboard/ExplainabilityCard";
import SystemHealthCard     from "@/components/dashboard/SystemHealthCard";
import MarketDataDashboard  from "@/components/dashboard/MarketDataDashboard";

export default function Home() {
  const [ticker, setTicker]               = useState("RELIANCE.NS");
  const [period, setPeriod]               = useState("1y");
  const [horizon, setHorizon]             = useState("5");
  const [currentInterval, setCurrentInterval] = useState("1d");
  const [marketStatus, setMarketStatus]   = useState(null);
  const [validationStats, setValidationStats] = useState(null);
  const [cacheInfo, setCacheInfo]         = useState(null);

  const {
    analysis,
    prediction,
    loading,
    error,
    runAnalysis,
    handleLogout,
    clearError,
  } = usePrediction();

  // Derived prediction data
  const { risk, portfolio, explain, signal } = useMemo(
    () => (prediction ? extractRiskPortfolio(prediction) : {}),
    [prediction]
  );

  const { dominant, probSideways, probSpikeUp, probSpikeDown } = useMemo(
    () => getDominantClass(prediction),
    [prediction]
  );

  const { beat: accBeat, tie: accTie, diff: accDiff } = useMemo(
    () => getAccuracyStatus(prediction),
    [prediction]
  );

  // Poll market data every 10 seconds
  useEffect(() => {
    let cancelled = false;

    const loadMarketData = async () => {
      try {
        const [status, validation, cache] = await Promise.all([
          getMarketStatus(),
          getValidationStats(),
          getCacheInfo(),
        ]);
        if (cancelled) return;
        setMarketStatus(status);
        setValidationStats(validation);
        setCacheInfo(cache);
      } catch (err) {
        if (!cancelled) console.warn("[index] market data refresh failed", err);
      }
    };

    loadMarketData();
    const timer = setInterval(loadMarketData, 10000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const handleRun = () => {
    runAnalysis(ticker, period, horizon);
  };

  return (
    <div className="page">

      {/* TOP BAR */}
      <TopBar
        marketStatus={marketStatus}
        onLogout={handleLogout}
      />

      {/* TICKER INPUT */}
      <div className="terminal-section">
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
      </div>

      {/* ERROR BANNER */}
      {error && (
        <div className="error-bar" onClick={clearError}>
          ⚠ {error} — click to dismiss
        </div>
      )}

      {/* MAIN GRID — 70 / 30 split */}
      <div className="two-col">

        {/* LEFT COLUMN — 70% */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* 1. Live Price Chart */}
          <LivePriceChart
            analysis={analysis}
            currentInterval={currentInterval}
            onIntervalChange={setCurrentInterval}
          />

          {/* 2. Prediction Engine */}
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
          />

          {/* 3. Trade Setup */}
          <TradeSetup
            risk={risk}
            portfolio={portfolio}
            signal={signal}
          />

        </div>

        {/* RIGHT COLUMN — 30% */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Portfolio */}
          <PortfolioCard
            portfolio={portfolio}
            risk={risk}
          />

          {/* Market Health */}
          <MarketHealthCard
            marketStatus={marketStatus}
            currentInterval={currentInterval}
          />

          {/* Model Diagnostics */}
          <ModelDiagnosticsCard
            prediction={prediction}
            dominant={dominant}
            accBeat={accBeat}
            accTie={accTie}
            accDiff={accDiff}
          />

          {/* Explainability */}
          <ExplainabilityCard
            explain={explain}
          />

          {/* Market Data Dashboard */}
          <MarketDataDashboard
            status={marketStatus}
            validationStats={validationStats}
            cacheInfo={cacheInfo}
            loading={!marketStatus && !validationStats && !cacheInfo}
            currentInterval={currentInterval}
            onIntervalChange={setCurrentInterval}
          />

        </div>
      </div>

      {/* BOTTOM — System Health */}
      <div style={{ marginTop: 16 }}>
        <SystemHealthCard
          validationStats={validationStats}
          cacheInfo={cacheInfo}
        />
      </div>

    </div>
  );
}
