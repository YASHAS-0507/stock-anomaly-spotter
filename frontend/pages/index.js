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

  return (
    <div className="page">
      <TopBar analysis={analysis} latency={latency} />

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
            <LivePriceChart analysis={analysis} />
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
    </div>
  );
}
