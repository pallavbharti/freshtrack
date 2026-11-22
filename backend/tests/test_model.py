import os

import pandas as pd

from app.ml.features import FEATURE_COLUMNS, build_training_frame, features_for_next_day
from app.ml.forecaster import wape

MAX_WAPE = float(os.getenv("MODEL_MAX_WAPE", "20"))
MAX_MAE = float(os.getenv("MODEL_MAX_MAE", "6.0"))


def test_model_wape_below_threshold(trained):
    _, metrics = trained
    assert metrics["model"]["wape"] < MAX_WAPE, metrics


def test_model_mae_below_threshold(trained):
    _, metrics = trained
    assert metrics["model"]["mae"] < MAX_MAE, metrics


def test_model_beats_naive_baseline(trained):
    _, metrics = trained
    assert metrics["model"]["wape"] < metrics["naive_lag7"]["wape"], metrics


def test_wape_handles_zero_sales():
    assert wape([0, 0, 10], [1, 0, 9]) == 20.0
    assert wape([0, 0], [0, 0]) == 0.0
    assert wape([10, 10], [10, 10]) == 0.0


def test_no_future_leakage_in_rolling_features(sales_df):
    frame = build_training_frame(sales_df)
    one = sales_df[sales_df["sku"] == "MLK-001"].reset_index(drop=True)
    row = frame[frame["sku"] == "MLK-001"].iloc[0]
    idx = one.index[pd.to_datetime(one["date"]) == row["date"]][0]
    assert row["roll_mean_7"] == one["quantity"].iloc[idx - 7: idx].mean()


def test_live_features_match_training_features(sales_df):
    frame = build_training_frame(sales_df)
    one = sales_df[sales_df["sku"] == "TOM-006"].reset_index(drop=True)
    row = frame[frame["sku"] == "TOM-006"].iloc[-1]
    idx = one.index[pd.to_datetime(one["date"]) == row["date"]][0]
    history = one["quantity"].iloc[:idx].tolist()

    live = features_for_next_day(history, row["date"], int(row["on_promo"]), int(row["is_holiday"]))
    for col in FEATURE_COLUMNS:
        assert abs(live[col] - row[col]) < 1e-9, col
