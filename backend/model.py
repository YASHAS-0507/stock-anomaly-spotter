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


def time_ordered_split(df: pd.DataFrame, test_fraction: float = 0.2):
    split_idx = int(len(df) * (1 - test_fraction))
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]
    return train_df, test_df


def train_direction_model(feature_df: pd.DataFrame, test_fraction: float = 0.2) -> ModelResult:
    train_df, test_df = time_ordered_split(feature_df, test_fraction)

    X_train, y_train = train_df[FEATURE_COLUMNS], train_df["next_day_up"]
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df["next_day_up"]

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=4,
        min_samples_leaf=10,
        random_state=42,
    )
    model.fit(X_train, y_train)
    preds = model.predict(X_test)

    # baseline: a classifier that always predicts the majority class.
    # any "real" model must beat this to mean anything at all.
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
        feature_importances=dict(zip(FEATURE_COLUMNS, np.round(model.feature_importances_, 4))),
    )
    return result


def predict_latest(model: RandomForestClassifier, feature_df: pd.DataFrame) -> dict:
    """
    Predicts direction for the most recent row available. Returns a
    probability, not a buy/sell instruction -- the caller decides how
    to present that responsibly.
    """
    latest = feature_df.iloc[[-1]][FEATURE_COLUMNS]
    proba = model.predict_proba(latest)[0]
    classes = model.classes_
    prob_up = float(proba[list(classes).index(1)]) if 1 in classes else 0.0
    return {
        "prob_up": round(prob_up, 4),
        "prob_down": round(1 - prob_up, 4),
        "predicted_direction": "up" if prob_up >= 0.5 else "down",
    }
