"""
intraday_model.py
-----------------
XGBoost binary classifier: will price be higher in 15 minutes?

Target:  future_price > current_price  →  1 (up)  else  0 (down)
Split:   time-ordered 80/20 (NEVER random shuffle)
Persist: backend/models/intraday_model.pkl
"""

import logging
import os
import pickle
import sys

logger = logging.getLogger(__name__)

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# MODEL_PATH env var → Railway Volume mount (e.g. /mnt/models/intraday_model.pkl).
# Falls back to backend/models/intraday_model.pkl when not set.
_DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intraday_model.pkl")
_MODEL_PATH = os.environ.get("MODEL_PATH", _DEFAULT_MODEL_PATH)

if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

try:
    import xgboost as xgb
    _XGB_OK = True
except ImportError:
    _XGB_OK = False
    xgb = None  # type: ignore

FEATURE_COLUMNS = [
    "price_vs_vwap_pct",
    "price_above_vwap",
    "ema9_above_ema21",
    "price_vs_ema21_pct",
    "rsi_14",
    "rsi_slope",
    "macd_histogram",
    "macd_crossover",
    "volume_ratio",
    "atr_pct",
    "bollinger_pct_b",
    "bollinger_squeeze",
    "return_zscore",
    "orb_breakout",
    "time_of_day_score",
    "higher_highs",
    "higher_lows",
    # ML feature expansion
    "vwap_deviation_pct",
    "orb_position",
    "volume_ratio_5min",
    "time_sin",
    "time_cos",
    "price_vs_prev_high",
    "tv_signal_score",
]

logger.info("[model] Feature set: %d features", len(FEATURE_COLUMNS))


class IntradayModel:
    """XGBoost intraday direction classifier with graceful fallbacks."""

    def __init__(self):
        self._model = None          # fitted XGBClassifier
        self._feature_importances: dict = {}

    # ──────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────

    def train(self, historical_candles: list) -> dict:
        """
        Train on time-ordered candle feature dicts.

        Each dict must contain all FEATURE_COLUMNS plus:
          current_price : float
          future_price  : float  (price 15 min ahead)

        Returns
        -------
        dict with accuracy, baseline_accuracy, n_train, n_test,
        feature_importances
        """
        if not _XGB_OK:
            raise RuntimeError("xgboost is not installed")

        if len(historical_candles) < 10:
            raise ValueError(f"Need at least 10 samples, got {len(historical_candles)}")

        X, y = self._build_dataset(historical_candles)

        # Time-ordered split — NO shuffling
        split  = int(len(X) * 0.80)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            verbosity=0,
            random_state=42,
        )
        model.fit(X_train, y_train)

        y_pred    = model.predict(X_test)
        accuracy  = float(sum(p == t for p, t in zip(y_pred, y_test)) / len(y_test))
        baseline  = float(max(sum(y_test), len(y_test) - sum(y_test)) / len(y_test))

        # Feature importances
        scores = model.feature_importances_
        importances = {col: round(float(scores[i]), 4)
                       for i, col in enumerate(FEATURE_COLUMNS)}

        self._model = model
        self._feature_importances = importances
        self._save()

        return {
            "accuracy":           round(accuracy, 4),
            "baseline_accuracy":  round(baseline, 4),
            "n_train":            len(X_train),
            "n_test":             len(X_test),
            "feature_importances": importances,
        }

    def predict(self, features: dict) -> dict:
        """
        Predict direction for the given feature dict.

        Returns prob_up, prob_down, predicted_direction, confidence_level.
        Falls back to 0.5/0.5 NEUTRAL when not trained.
        Never raises.
        """
        try:
            return self._predict(features)
        except Exception as exc:
            logger.warning("[model] predict() failed: %s", exc)
            return _neutral_result()

    def get_training_data(
        self,
        tickers: list,
        days_back: int = 60,
    ) -> list:
        """
        Fetches 5-min candles from data_provider for multiple tickers
        and builds a training dataset.

        Each sample dict has all FEATURE_COLUMNS plus current_price
        and future_price (price 15 min = 3 bars ahead).

        Falls back to synthetic data if Angel One unavailable.
        """
        try:
            from feeds.data_provider import data_provider
            from indicators.intraday_features import IntradayFeatures
            fc = IntradayFeatures()
            all_samples: list = []

            for ticker in tickers:
                try:
                    candles, source = data_provider.get_intraday_candles(
                        ticker, interval="FIVE_MINUTE", days_back=days_back
                    )
                    if len(candles) < 45:
                        logger.debug(
                            "[model] Skipping %s — only %d candles from %s",
                            ticker, len(candles), source,
                        )
                        continue

                    horizon = 3   # 15 min ahead
                    window  = 40  # min candles for stable features

                    for i in range(window, len(candles) - horizon):
                        try:
                            cur_price = float(candles[i]["close"])
                            fut_price = float(candles[i + horizon]["close"])
                            feats = fc.compute(candles[:i], [], cur_price)
                            feats["current_price"] = cur_price
                            feats["future_price"]  = fut_price
                            all_samples.append(feats)
                        except Exception:
                            continue

                except Exception as exc:
                    logger.debug("[model] Training data fetch failed for %s: %s", ticker, exc)

            if all_samples:
                logger.info(
                    "[model] Built %d training samples from %d tickers via data_provider",
                    len(all_samples), len(tickers),
                )
                return all_samples

        except Exception as exc:
            logger.warning("[model] get_training_data() failed: %s — using synthetic", exc)

        return self._synthetic_training_data(tickers)

    def _synthetic_training_data(self, tickers: list) -> list:
        """Generate deterministic synthetic training data as fallback."""
        import random
        try:
            from indicators.intraday_features import IntradayFeatures
            fc = IntradayFeatures()
        except Exception:
            return []

        all_samples: list = []
        for ticker in tickers[:5]:
            seed = sum(ord(c) for c in ticker)
            rng  = random.Random(seed)
            base = 100.0 + rng.uniform(0, 900)

            candles = []
            price = base
            for i in range(200):
                o = price
                c = o * (1 + rng.gauss(0, 0.002))
                h = max(o, c) * (1 + abs(rng.gauss(0, 0.001)))
                l = min(o, c) * (1 - abs(rng.gauss(0, 0.001)))
                candles.append({
                    "timestamp": float(1700000000 + i * 300),
                    "open":  round(o, 2), "high": round(h, 2),
                    "low":   round(l, 2), "close": round(c, 2),
                    "volume": rng.randint(10000, 1000000),
                })
                price = c

            horizon, window = 3, 40
            for i in range(window, len(candles) - horizon):
                try:
                    cur_price = float(candles[i]["close"])
                    fut_price = float(candles[i + horizon]["close"])
                    feats = fc.compute(candles[:i], [], cur_price)
                    feats["current_price"] = cur_price
                    feats["future_price"]  = fut_price
                    all_samples.append(feats)
                except Exception:
                    continue

        return all_samples

    def load(self) -> bool:
        """
        Load model from disk.

        Returns True if loaded successfully, False otherwise.
        """
        if not os.path.exists(_MODEL_PATH):
            return False
        try:
            with open(_MODEL_PATH, "rb") as fh:
                data = pickle.load(fh)
            self._model               = data["model"]
            self._feature_importances = data.get("feature_importances", {})
            logger.info("[model] Loaded from %s", _MODEL_PATH)
            return True
        except Exception as exc:
            logger.warning("[model] Load failed: %s", exc)
            return False

    def is_trained(self) -> bool:
        """Return True if the model is ready for predictions."""
        return self._model is not None

    # ──────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────

    def _predict(self, features: dict) -> dict:
        if self._model is None:
            return _neutral_result()

        row = [float(bool(features.get(col, 0)) if isinstance(features.get(col), bool)
                     else features.get(col, 0.0) or 0.0)
               for col in FEATURE_COLUMNS]

        proba    = self._model.predict_proba([row])[0]
        prob_up  = float(proba[1])
        prob_down = float(proba[0])

        direction = "up" if prob_up >= 0.5 else "down"

        if prob_up > 0.65:
            confidence = "HIGH"
        elif prob_up > 0.55:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return {
            "prob_up":              round(prob_up,   4),
            "prob_down":            round(prob_down, 4),
            "predicted_direction":  direction,
            "confidence_level":     confidence,
        }

    @staticmethod
    def _build_dataset(candles: list) -> tuple:
        """Extract feature matrix X and label vector y (time-ordered)."""
        X, y = [], []
        for c in candles:
            cp = c.get("current_price")
            fp = c.get("future_price")
            if cp is None or fp is None:
                continue
            try:
                row = []
                for col in FEATURE_COLUMNS:
                    val = c.get(col, 0.0)
                    # Coerce booleans to 0/1
                    if isinstance(val, bool):
                        val = 1.0 if val else 0.0
                    row.append(float(val) if val is not None else 0.0)
                X.append(row)
                y.append(1 if float(fp) > float(cp) else 0)
            except (TypeError, ValueError):
                continue
        return X, y

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
            with open(_MODEL_PATH, "wb") as fh:
                pickle.dump({
                    "model":               self._model,
                    "feature_importances": self._feature_importances,
                }, fh)
            logger.info("[model] Saved to %s", _MODEL_PATH)
        except Exception as exc:
            logger.warning("[model] Save failed: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _neutral_result() -> dict:
    return {
        "prob_up":             0.5,
        "prob_down":           0.5,
        "predicted_direction": "up",
        "confidence_level":    "LOW",
    }


# Module-level singleton
intraday_model = IntradayModel()
