# Stock anomaly spotter

A data science project that combines real technical-analysis Python (≈80% of the work)
with a thin Next.js dashboard on top.

## What it actually does (read this before the report)

1. **Anomaly detection** — flags days where the daily return is a statistical outlier
   relative to its own recent 20-day volatility (rolling z-score). This is real and reliable.
2. **Direction prediction** — a RandomForestClassifier trained on technical indicators
   (RSI, moving average crossover, volatility, volume ratio, return z-score) predicts
   whether tomorrow's close will be higher or lower than today's.
3. **Chart screenshot reader** — basic computer vision (no ML model) traces the visible
   line in an uploaded chart image and reports whether the visible trend is rising,
   falling, or flat.

## What it deliberately does NOT do

- It does **not** claim 90%+ prediction accuracy. Short-term stock direction is close to
  a random walk; a time-ordered, leakage-free backtest on this kind of feature set
  typically lands around 50-58% accuracy. Any project that claims much higher than that
  without proof of a non-leaking pipeline should be treated with suspicion — that's the
  single most common mistake in student stock-prediction projects.
- It does **not** output "buy" or "sell" instructions. It reports a probability and lets
  the reader interpret it. This is a deliberate, documented choice — see `model.py` and
  `chart_reader.py` docstrings.
- The chart reader cannot recover the real price scale or ticker from a screenshot —
  only the visible trend shape.

## Project structure

```
backend/
  data_pipeline.py   # fetch real data (yfinance) with synthetic fallback
  features.py         # technical indicators
  anomaly.py           # rolling z-score anomaly detection
  model.py             # RandomForest direction classifier, time-ordered split
  chart_reader.py     # screenshot -> trend extraction (OpenCV/PIL-free, numpy-based)
  app.py                # FastAPI app tying it together
  requirements.txt
frontend/
  pages/index.js        # dashboard UI (Next.js + recharts)
  styles/globals.css
  package.json
```

## Running it locally

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local
npm run dev
```

Then open http://localhost:3000.

## Deploying (matches your existing Quilzo pipeline)

- Backend: Railway, same as your `xeroxgo-bot` deploy. Add a `Procfile` with
  `web: uvicorn app:app --host 0.0.0.0 --port $PORT` if Railway needs it.
- Frontend: Vercel, set `NEXT_PUBLIC_API_BASE` to your Railway backend URL.

## For your report

Good sections to include:
- **Problem framing**: anomaly detection (solved well) vs direction prediction
  (inherently hard, report it honestly)
- **Methodology**: feature engineering, time-ordered split and why a random split
  would have leaked information
- **Results**: test accuracy vs majority-class baseline — the gap (however small)
  is the real signal, not the raw accuracy number
- **Limitations**: market regime changes, no fundamental/news data, screenshot
  reader's scale-recovery limits
- **Ethical note**: not used for real trading decisions; no buy/sell automation

Send me your report format whenever you have it and I'll fill it in with these
results and a methodology write-up.
