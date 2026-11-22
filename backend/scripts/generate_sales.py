import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog import PRODUCTS  # noqa: E402

DEFAULT_END = date(2026, 6, 30)

WEEKDAY_FACTOR = [0.90, 0.85, 0.90, 0.95, 1.05, 1.25, 1.20]


def generate(days: int, seed: int = 42, end: date | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    end = end or DEFAULT_END
    start = end - timedelta(days=days - 1)
    dates = pd.date_range(start, end, freq="D")

    holidays = set(rng.choice(len(dates), size=max(1, days * 12 // 365), replace=False))

    rows = []
    for p in PRODUCTS:
        sku, base = p["sku"], p["avg_daily_demand"]
        phase = rng.uniform(0, 2 * np.pi)
        promo_days = rng.random(len(dates)) < 0.06

        for i, d in enumerate(dates):
            mean = base * WEEKDAY_FACTOR[d.weekday()]
            mean *= 1 + 0.10 * np.sin(2 * np.pi * i / 365 + phase)
            mean *= 1 + 0.0002 * i
            if i in holidays:
                mean *= 1.6
            if promo_days[i]:
                mean *= 1.35
            qty = rng.poisson(mean)
            rows.append(
                {
                    "date": d.date().isoformat(),
                    "sku": sku,
                    "quantity": int(qty),
                    "on_promo": int(promo_days[i]),
                    "is_holiday": int(i in holidays),
                }
            )

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END, help="last date, YYYY-MM-DD")
    parser.add_argument("--out", default="data/sales.csv")
    args = parser.parse_args()

    df = generate(args.days, args.seed, args.end)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, lineterminator="\n")
    print(f"wrote {len(df)} rows to {out}")


if __name__ == "__main__":
    main()
