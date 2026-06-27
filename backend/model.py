"""
model.py
--------
Trains a classifier that predicts next-day price DIRECTION (up/down)
from technical indicator features.

Honesty notes, on purpose, for the report:
- Split is TIME-ORDERED (train on the past, test on the future). A random
  shuffle split would leak future information into training and inflate
  accuracy artificially -- a very common mistake in toy stock-prediction
  projects that is the #1 reason their reported "90%+ accuracy" numbers
  are not real.
- The model predicts DIRECTION only, not magnitude, and direction alone
  is close to a coin flip on liquid markets in the short term. A real
  accuracy in the 50-58% range on the held-out test set is a believable,
  defensible result. Treat any much higher number as a red flag for a
  leaked or overfit pipeline.
- This is a class project / portfolio piece, not a trading system. It
  must not be used to make real buy/sell decisions.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.dummy import DummyClassifier

from features import FEATURE_COLUMNS


@dataclass
class ModelResult:
    model: RandomForestClassifier
    accuracy: float
    baseline_accuracy: float
    precision: float
    recall: float
    f1: float
    n_train: int
    n_test: int
    feature_importances: dict
    selected_features: list = None
    

def time_ordered_split(df: pd.DataFrame, test_fraction: float = 0.2):
    split_idx = int(len(df) * (1 - test_fraction))
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]
    return train_df, test_df


def train_direction_model(feature_df: pd.DataFrame, test_fraction: float = 0.2, top_k_features: int = 8) -> ModelResult:
    train_df, test_df = time_ordered_split(feature_df, test_fraction)

    X_train_full, y_train = train_df[FEATURE_COLUMNS], train_df["next_day_up"]
    X_test_full, y_test = test_df[FEATURE_COLUMNS], test_df["next_day_up"]

    # Feature selection: with ~20 features and only ~150-250 rows, fitting on
    # all of them invites overfitting (curse of dimensionality). We fit a
    # quick exploratory model on the TRAINING set only (never touches test
    # data, so this doesn't leak) to rank feature importance, then keep only
    # the top_k most useful features for the real model. This is a standard
    # technique, not cheating -- the selection decision is made without ever
    # looking at the held-out test set.
    selector = RandomForestClassifier(
        n_estimators=200, max_depth=4, min_samples_leaf=10, random_state=42
    )
    selector.fit(X_train_full, y_train)
    importances = pd.Series(selector.feature_importances_, index=FEATURE_COLUMNS)
    selected_features = importances.sort_values(ascending=False).head(top_k_features).index.tolist()

    X_train, X_test = X_train_full[selected_features], X_test_full[selected_features]

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=3,
        min_samples_leaf=15,
        max_features="sqrt",
        random_state=42,
    )
    model.fit(X_train, y_train)
    preds = model.predict(X_test)

    baseline = DummyClassifier(strategy="most_frequent")
    baseline.fit(X_train, y_train)
    baseline_preds = baseline.predict(X_test)

    result = ModelResult(
        model=model,
        accuracy=round(accuracy_score(y_test, preds), 4),
        baseline_accuracy=round(accuracy_score(y_test, baseline_preds), 4),
        precision=round(precision_score(y_test, preds, zero_division=0), 4),
        recall=round(recall_score(y_test, preds, zero_division=0), 4),
        f1=round(f1_score(y_test, preds, zero_division=0), 4),
        n_train=len(train_df),
        n_test=len(test_df),
        feature_importances=dict(zip(selected_features, np.round(model.feature_importances_, 4))),
        selected_features=selected_features,
    )
    return result


def predict_latest(model: RandomForestClassifier, feature_df: pd.DataFrame, selected_features: list = None) -> dict:
    """
    Predicts direction for the most recent row available. Returns a
    probability, not a buy/sell instruction -- the caller decides how
    to present that responsibly.
    """
    cols = selected_features if selected_features else FEATURE_COLUMNS
    latest = feature_df.iloc[[-1]][cols]
    proba = model.predict_proba(latest)[0]
    classes = model.classes_
    prob_up = float(proba[list(classes).index(1)]) if 1 in classes else 0.0
    return {
        "prob_up": round(prob_up, 4),
        "prob_down": round(1 - prob_up, 4),
        "predicted_direction": "up" if prob_up >= 0.5 else "down",
    }
# =====================================================================
# PRODUCTION INFERENCE INTEGRATION LAYER
# =====================================================================

class InferenceEngine:
    def __init__(self):
        self.model_version = "v1.0.0-rf"
        self._trained_model = None
        self._selected_features = None

    def initialize_production_model(self, feature_df: pd.DataFrame):
        """
        Trains the internal model instance on available history so it's
        warmed up and ready for live endpoint queries.
        """
        try:
            print("[model] Initializing production Random Forest classifier...")
            result = train_direction_model(feature_df, test_fraction=0.15)
            self._trained_model = result.model
            self._selected_features = result.selected_features
            print(f"[model] Initialization successful. Metrics -> Accuracy: {result.accuracy}, Features: {self._selected_features}")
        except Exception as e:
            print(f"[model] Core compilation failed: {str(e)}. Falling back to baseline configuration.")
            self._trained_model = None

    def predict_anomaly_probability(self, feature_df: pd.DataFrame) -> float:
        """
        Exposes a standardized interface for app.py to get win probabilities.
        """
        # Fallback if model training failed or dataframe is sparse
        if self._trained_model is None or feature_df is None or feature_df.empty:
            return 0.50

        try:
            # Re-use your existing prediction routine safely
            prediction_payload = predict_latest(
                model=self._trained_model, 
                feature_df=feature_df, 
                selected_features=self._selected_features
            )
            return float(prediction_payload["prob_up"])
        except Exception as e:
            print(f"[model] Live inference error: {str(e)}. Defaulting to 0.50 neutral risk bounds.")
            return 0.50

# Instantiate a persistent singleton instance for Dependency Injection
intelligence_core = InferenceEngine()