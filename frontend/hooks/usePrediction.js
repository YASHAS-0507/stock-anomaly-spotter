import { useState, useCallback } from "react";
import { analyze, predict, uploadChartImage, logout } from "@/services/api";

export function usePrediction() {
  const [analysis, setAnalysis] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [chartTrend, setChartTrend] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [drag, setDrag] = useState(false);

  const runAnalysis = useCallback(async (ticker, period, horizon) => {
    setLoading(true);
    setError(null);
    try {
      const [aRes, pRes] = await Promise.all([
        analyze(ticker, period),
        predict(ticker, period, horizon)
      ]);
      setAnalysis(aRes);
      setPrediction(pRes);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleUploadChart = useCallback(async (file) => {
    if (!file) return;
    setError(null);
    try {
      const res = await uploadChartImage(file);
      setChartTrend(res);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const handleLogout = useCallback(async () => {
    await logout();
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return {
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
  };
}