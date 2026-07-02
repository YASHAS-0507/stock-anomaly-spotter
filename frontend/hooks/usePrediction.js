import { useState } from "react";
import { fetchAnalysis, fetchPrediction } from "../services/api";

export function usePrediction() {
  const [ticker, setTicker] = useState("RELIANCE.NS");
  const [period, setPeriod] = useState("1y");
  const [horizon, setHorizon] = useState(5);
  const [chartInterval, setChartInterval] = useState("1d");
  const [analysis, setAnalysis] = useState(null);
  const [prediction, setPrediction] = useState(null);
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
    analysis, prediction,
    loading, error, latency,
    runAnalysis,
  };
}
