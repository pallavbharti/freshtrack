import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from ..integrity import write_manifest
from . import drift
from .features import FEATURE_COLUMNS, build_training_frame, features_for_next_day

TEST_DAYS = 60
MAX_HORIZON_DAYS = 30


def wape(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    total = y_true.sum()
    if total <= 0:
        return 0.0 if np.allclose(y_pred, 0) else float("inf")
    return float(np.abs(y_true - y_pred).sum() / total * 100)


def _metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    err = y_true - y_pred
    nz = y_true > 0
    return {
        "mae": round(float(np.mean(np.abs(err))), 3),
        "rmse": round(float(np.sqrt(np.mean(err ** 2))), 3),
        "wape": round(wape(y_true, y_pred), 2),
        "mape": round(float(np.mean(np.abs(err[nz] / y_true[nz])) * 100), 2),
    }


def train(sales: pd.DataFrame, test_days: int = TEST_DAYS) -> tuple[GradientBoostingRegressor, dict]:
    frame = build_training_frame(sales)
    cutoff = frame["date"].max() - pd.Timedelta(days=test_days)
    train_df = frame[frame["date"] <= cutoff]
    test_df = frame[frame["date"] > cutoff]

    model = GradientBoostingRegressor(
        n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.9, random_state=7
    )
    model.fit(train_df[FEATURE_COLUMNS], train_df["quantity"])

    preds = model.predict(test_df[FEATURE_COLUMNS])

    served = test_df.copy()
    served[["on_promo", "is_holiday"]] = 0
    served_preds = model.predict(served[FEATURE_COLUMNS])

    per_sku = {}
    reference = {}
    for sku, g in test_df.assign(pred=served_preds).groupby("sku"):
        per_sku[sku] = round(wape(g["quantity"], g["pred"]), 2)
    for sku, g in train_df.groupby("sku"):
        reference[sku] = drift.build_reference(g.sort_values("date")["quantity"].tail(drift.REFERENCE_DAYS))

    metrics = {
        "model": _metrics(test_df["quantity"], preds),
        "naive_lag7": _metrics(test_df["quantity"], test_df["lag_7"]),
        "model_as_served": _metrics(test_df["quantity"], served_preds),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "test_days": test_days,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "holdout_wape_by_sku": per_sku,
        "reference_distribution": reference,
    }
    return model, metrics


def save(model, metrics: dict, path: Path, data_path: Path | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURE_COLUMNS, "metrics": metrics}, path)
    metrics_path = path.with_suffix(".metrics.json")
    metrics_path.write_text(json.dumps(metrics, indent=2))
    write_manifest(path, metrics_path, data_path)


class Forecaster:
    def __init__(self, model_path: Path):
        model_path = Path(model_path)
        self.version = hashlib.sha256(model_path.read_bytes()).hexdigest()[:12]
        bundle = joblib.load(model_path)
        self.model = bundle["model"]
        self.features = bundle["features"]
        self.metrics = bundle.get("metrics", {})

    def forecast(self, history: list[float], start: date, days: int) -> list[dict]:
        days = int(days)
        if not 1 <= days <= MAX_HORIZON_DAYS:
            raise ValueError(f"days must be between 1 and {MAX_HORIZON_DAYS}, got {days}")
        hist = list(history)
        out = []
        for i in range(days):
            d = pd.Timestamp(start + timedelta(days=i))
            row = features_for_next_day(hist, d)
            x = pd.DataFrame([row])[self.features]
            pred = max(0.0, float(self.model.predict(x)[0]))
            out.append({"date": d.date().isoformat(), "predicted_qty": round(pred, 1)})
            hist.append(pred)
        return out
