import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import inventory  # noqa: E402
from app.catalog import PRODUCTS  # noqa: E402
from app.ml.features import FEATURE_COLUMNS, features_for_next_day  # noqa: E402
from app.ml.forecaster import TEST_DAYS, train  # noqa: E402
from scripts.generate_sales import DEFAULT_END, generate  # noqa: E402

WINDOW = 7
Z = 1.65
DATA_SEED = 42
DATA_DAYS = 730
POLICIES = ("replenish", "baseline", "ours")


@dataclass
class Shelf:
    batches: list = field(default_factory=list)
    pipeline: list = field(default_factory=list)
    received: int = 0
    sold: int = 0
    lost: int = 0
    expired: int = 0
    stockout_days: int = 0

    def on_hand(self):
        return sum(q for _, q in self.batches)

    def on_order(self):
        return sum(q for _, q in self.pipeline)


def run_day(shelf: Shelf, day, demand: int, shelf_life: int):
    arrived = [p for p in shelf.pipeline if p[0] <= day]
    shelf.pipeline = [p for p in shelf.pipeline if p[0] > day]
    for _, qty in arrived:
        shelf.batches.append([day + timedelta(days=shelf_life), qty])
        shelf.received += qty
    shelf.batches.sort(key=lambda b: b[0])

    while shelf.batches and shelf.batches[0][0] < day:
        shelf.expired += shelf.batches.pop(0)[1]

    left = demand
    while left and shelf.batches:
        take = min(left, shelf.batches[0][1])
        shelf.batches[0][1] -= take
        left -= take
        if shelf.batches[0][1] == 0:
            shelf.batches.pop(0)
    shelf.sold += demand - left
    shelf.lost += left
    if left:
        shelf.stockout_days += 1


def replenish_order(sold_today: int) -> int:
    return sold_today


def baseline_order(shelf: Shelf, history: list[float], lead: int) -> int:
    target = np.mean(history[-28:]) * (lead + 1) * 1.2
    return max(0, math.ceil(target - shelf.on_hand() - shelf.on_order()))


def our_order(shelf: Shelf, history: list[float], lead: int, day, model, shelf_life: int) -> int:
    tomorrow = day + timedelta(days=1)
    daily = model.forecast(history, tomorrow, WINDOW)

    batches = [inventory.Batch(q, e) for e, q in shelf.batches]
    batches += [inventory.Batch(q, a + timedelta(days=shelf_life)) for a, q in shelf.pipeline]

    rec = inventory.plan_order(daily, batches, lead, float(np.std(history[-28:], ddof=1)), tomorrow, Z)
    return rec["qty"] if rec["action"] == "REORDER" else 0


class InMemoryModel:
    def __init__(self, sk_model):
        self.m = sk_model

    def forecast(self, history, start, days) -> list[float]:
        hist = list(history)
        out = []
        for i in range(days):
            d = pd.Timestamp(start + timedelta(days=i))
            x = pd.DataFrame([features_for_next_day(hist, d)])[FEATURE_COLUMNS]
            p = max(0.0, float(self.m.predict(x)[0]))
            out.append(p)
            hist.append(p)
        return out


def simulate(sales: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    sk_model, model_metrics = train(sales)
    model = InMemoryModel(sk_model)

    sales = sales.copy()
    sales["date"] = pd.to_datetime(sales["date"]).dt.date
    start = max(sales["date"]) - timedelta(days=TEST_DAYS - 1)

    rows = []
    for p in PRODUCTS:
        s = sales[sales["sku"] == p["sku"]].sort_values("date")
        hist_all = s["quantity"].astype(float).tolist()
        dates = s["date"].tolist()
        first = dates.index(start)
        lead = max(1, p["lead_time_days"])

        for policy in POLICIES:
            shelf = Shelf()
            opening = round(np.mean(hist_all[first - 28:first]) * 2)
            shelf.batches.append([start + timedelta(days=p["shelf_life_days"] - 1), opening])
            shelf.received += opening

            for i in range(first, len(dates)):
                day = dates[i]
                sold_before = shelf.sold
                run_day(shelf, day, int(hist_all[i]), p["shelf_life_days"])
                history = hist_all[: i + 1]
                if policy == "replenish":
                    qty = replenish_order(shelf.sold - sold_before)
                elif policy == "baseline":
                    qty = baseline_order(shelf, history, lead)
                else:
                    qty = our_order(shelf, history, lead, day, model, p["shelf_life_days"])
                if qty:
                    shelf.pipeline.append([day + timedelta(days=lead), qty])

            demand = shelf.sold + shelf.lost
            rows.append({
                "sku": p["sku"],
                "policy": policy,
                "days": len(dates) - first,
                "demand": demand,
                "received": shelf.received,
                "sold": shelf.sold,
                "lost_sales": shelf.lost,
                "stockout_days": shelf.stockout_days,
                "expired": shelf.expired,
                "fill_rate_pct": round(100 * shelf.sold / demand, 2) if demand else 100.0,
                "waste_rate_pct": round(100 * shelf.expired / shelf.received, 2) if shelf.received else 0.0,
            })
    return pd.DataFrame(rows), model_metrics


def kpis(df: pd.DataFrame) -> dict:
    out = {}
    for policy in POLICIES:
        g = df[df["policy"] == policy]
        demand, received = int(g["demand"].sum()), int(g["received"].sum())
        out[policy] = {
            "waste_rate": round(100 * g["expired"].sum() / received, 3) if received else 0.0,
            "fill_rate": round(100 * g["sold"].sum() / demand, 3) if demand else 100.0,
            "stockout_days": int(g["stockout_days"].sum()),
            "lost_sales": int(g["lost_sales"].sum()),
            "expired_units": int(g["expired"].sum()),
            "received_units": received,
            "demand_units": demand,
        }
    return out


COMMITTED_DATA = Path(__file__).resolve().parents[1] / "data" / "sales.csv"


def load_or_generate(path: str | None) -> tuple[pd.DataFrame, str]:
    if path:
        return pd.read_csv(path), str(path)
    if COMMITTED_DATA.exists():
        return pd.read_csv(COMMITTED_DATA), "backend/data/sales.csv"
    return generate(DATA_DAYS, seed=DATA_SEED, end=DEFAULT_END), f"generated(seed={DATA_SEED}, end={DEFAULT_END})"


def build_report(sales: pd.DataFrame, source: str) -> tuple[pd.DataFrame, dict]:
    df, model_metrics = simulate(sales)
    csv_bytes = sales.to_csv(index=False, lineterminator="\n").encode()
    report = {
        "note": "Simulated on synthetic data. Not results from a real store.",
        "units": {"waste_rate": "percent", "fill_rate": "percent"},
        "data": {
            "source": source,
            "rows": int(len(sales)),
            "sha256": hashlib.sha256(csv_bytes).hexdigest(),
        },
        "test_days": TEST_DAYS,
        "forecast_wape": model_metrics["model"]["wape"],
        "policies": kpis(df),
    }
    return df, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="sales CSV; default: backend/data/sales.csv, or generate the fixed dataset")
    parser.add_argument("--out", help="per-product CSV output")
    parser.add_argument("--json", help="KPI JSON output")
    parser.add_argument("--quiet", action="store_true", help="only print the totals table")
    args = parser.parse_args()

    sales, source = load_or_generate(args.data)
    df, report = build_report(sales, source)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.out, index=False)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")

    if not args.quiet:
        print(df.to_string(index=False))
        print()
    print("Totals (simulated on synthetic data):")
    print(pd.DataFrame(report["policies"]).T.to_string())
    if args.json:
        print(f"\nKPI JSON written to {args.json}")


if __name__ == "__main__":
    main()
