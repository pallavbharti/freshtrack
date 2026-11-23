import numpy as np
import pandas as pd

LAGS = (1, 7, 14)
MIN_HISTORY_DAYS = 28

FEATURE_COLUMNS = [
    "lag_1",
    "lag_7",
    "lag_14",
    "roll_mean_7",
    "roll_mean_28",
    "roll_std_7",
    "day_of_week",
    "is_weekend",
    "on_promo",
    "is_holiday",
]


def build_training_frame(sales: pd.DataFrame) -> pd.DataFrame:
    df = sales.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["sku", "date"]).reset_index(drop=True)

    g = df.groupby("sku")["quantity"]
    for lag in LAGS:
        df[f"lag_{lag}"] = g.shift(lag)

    past = g.shift(1)
    df["roll_mean_7"] = past.groupby(df["sku"]).transform(lambda s: s.rolling(7).mean())
    df["roll_mean_28"] = past.groupby(df["sku"]).transform(lambda s: s.rolling(28).mean())
    df["roll_std_7"] = past.groupby(df["sku"]).transform(lambda s: s.rolling(7).std())

    df["day_of_week"] = df["date"].dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    return df.dropna(subset=FEATURE_COLUMNS).reset_index(drop=True)


def features_for_next_day(history: list[float], next_date: pd.Timestamp,
                          on_promo: int = 0, is_holiday: int = 0) -> dict:
    if len(history) < MIN_HISTORY_DAYS:
        raise ValueError(f"need at least {MIN_HISTORY_DAYS} days of history, got {len(history)}")

    h = np.asarray(history, dtype=float)
    dow = next_date.dayofweek
    return {
        "lag_1": h[-1],
        "lag_7": h[-7],
        "lag_14": h[-14],
        "roll_mean_7": h[-7:].mean(),
        "roll_mean_28": h[-28:].mean(),
        "roll_std_7": h[-7:].std(ddof=1),
        "day_of_week": dow,
        "is_weekend": int(dow >= 5),
        "on_promo": on_promo,
        "is_holiday": is_holiday,
    }
