import { useState } from "react";
import { fetchAnalysis, fetchPrediction, fetchDecision } from "../services/api";

export function usePrediction() {
  const [ticker, setTicker] = useState("RELIANCE.NS");
  const [period, setPeriod] = useState("1y");
  const [horizon, setHorizon] = useState(5);
  const [chartInterval, setChartInterval] = useState("1d");
  const [analysis, setAnalysis] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [decision, setDecision] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [latency, setLatency] = useState(null);

  async function runAnalysis() {
    setLoading(true);
    setError(null);
    const t0 = Date.now();
    try {
      const [aData, pData] = await Promise.all([
        fetchAnalysis(ticker, period),
        fetchPrediction(ticker, period, horizon),
      ]);
      setLatency(Date.now() - t0);
      setAnalysis(aData);
      setPrediction(pData);

      // Decision engine runs after prediction resolves (not blocking the main pair)
      try {
        const dData = await fetchDecision(ticker, period, horizon);
        setDecision(dData);
      } catch (_) {
        setDecision(null);
      }
    } catch (e) {
      setError(e.message);
      setLatency(null);
    } finally {
      setLoading(false);
    }
  }

  return {
    ticker, setTicker,
    period, setPeriod,
    horizon, setHorizon,
    chartInterval, setChartInterval,
    analysis, prediction, decision,
    loading, error, latency,
    runAnalysis,
  };
}
