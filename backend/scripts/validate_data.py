import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml import drift  # noqa: E402

COLUMNS = ["date", "sku", "quantity", "on_promo", "is_holiday"]
MIN_DAYS_PER_SKU = 90
MAX_MISSING_DAY_SHARE = 0.05
MIN_ROW_RATIO = 0.9
MAX_MEAN_RATIO = 3.0
SPIKE_FACTOR = 10.0
RECENT_DAYS = 90


def profile(df: pd.DataFrame, csv_bytes: bytes) -> dict:
    df = df.assign(date=pd.to_datetime(df["date"]))
    skus = {}
    for sku, g in df.sort_values("date").groupby("sku"):
        recent = g["quantity"].tail(RECENT_DAYS)
        skus[sku] = {
            "rows": int(len(g)),
            "first": g["date"].min().date().isoformat(),
            "last": g["date"].max().date().isoformat(),
            "recent_mean": round(float(recent.mean()), 3),
            "p99": float(np.quantile(g["quantity"], 0.99)),
            "max": int(g["quantity"].max()),
            "reference": drift.build_reference(recent),
        }
    return {"sha256": hashlib.sha256(csv_bytes).hexdigest(), "rows": int(len(df)), "skus": skus}


def validate(df: pd.DataFrame, ref: dict | None) -> tuple[list[str], list[str]]:
    errors, warnings = [], []

    if list(df.columns) != COLUMNS:
        return [f"columns are {list(df.columns)}, expected {COLUMNS}"], warnings
    dates = pd.to_datetime(df["date"], errors="coerce", format="%Y-%m-%d")
    if dates.isna().any():
        errors.append(f"{int(dates.isna().sum())} rows have an invalid date")
    qty = pd.to_numeric(df["quantity"], errors="coerce")
    if qty.isna().any() or (qty % 1 != 0).any():
        errors.append("quantity must be a whole number on every row")
    for col in ("on_promo", "is_holiday"):
        if not df[col].isin([0, 1]).all():
            errors.append(f"{col} must be 0 or 1")
    if errors:
        return errors, warnings
    df = df.assign(date=dates, quantity=qty.astype(int))

    neg = int((df["quantity"] < 0).sum())
    if neg:
        errors.append(f"{neg} rows have a negative quantity")
    dup = int(df.duplicated(["date", "sku"]).sum())
    if dup:
        errors.append(f"{dup} duplicate (date, sku) rows")

    for sku, g in df.groupby("sku"):
        span = (g["date"].max() - g["date"].min()).days + 1
        if len(g) < MIN_DAYS_PER_SKU:
            errors.append(f"{sku}: only {len(g)} days of history (need {MIN_DAYS_PER_SKU})")
        missing = 1 - g["date"].nunique() / span
        if missing > MAX_MISSING_DAY_SHARE:
            errors.append(f"{sku}: {missing:.0%} of days are missing")

    if ref is None:
        return errors, warnings

    if len(df) < MIN_ROW_RATIO * ref["rows"]:
        errors.append(f"only {len(df)} rows, previous dataset had {ref['rows']}")

    known = set(ref["skus"])
    for sku in sorted(set(df["sku"]) - known):
        warnings.append(f"{sku}: new product, no previous data to compare with")
    for sku in sorted(known - set(df["sku"])):
        warnings.append(f"{sku}: missing from the new data")

    for sku, g in df.sort_values("date").groupby("sku"):
        if sku not in known:
            continue
        prev = ref["skus"][sku]
        recent = g["quantity"].tail(RECENT_DAYS)
        if prev["p99"] > 0 and g["quantity"].max() > SPIKE_FACTOR * prev["p99"]:
            errors.append(f"{sku}: max {g['quantity'].max()} is more than {SPIKE_FACTOR:g}x the previous p99 "
                          f"({prev['p99']:g})")
        if prev["recent_mean"] > 0:
            ratio = recent.mean() / prev["recent_mean"]
            if ratio > MAX_MEAN_RATIO or ratio < 1 / MAX_MEAN_RATIO:
                errors.append(f"{sku}: recent mean {recent.mean():.1f} vs {prev['recent_mean']:.1f} before "
                              f"({ratio:.2f}x) - looks like corrupted or poisoned data")
        score = drift.psi(prev["reference"], recent)
        if score > 0.25:
            warnings.append(f"{sku}: demand pattern changed (PSI {score:.2f}) - expected when retraining on new data")

    return errors, warnings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--reference", help="profile JSON of the previous dataset")
    parser.add_argument("--write-profile", help="write this dataset's profile here (only if it is valid)")
    parser.add_argument("--summary", help="append a markdown report (e.g. $GITHUB_STEP_SUMMARY)")
    args = parser.parse_args()

    raw = Path(args.csv).read_bytes()
    df = pd.read_csv(args.csv)
    ref = json.loads(Path(args.reference).read_text()) if args.reference else None
    errors, warnings = validate(df, ref)

    lines = [f"## Data validation: {'FAILED' if errors else 'PASSED'} ({len(df)} rows)", ""]
    lines += [f"- ❌ {e}" for e in errors] + [f"- ⚠️ {w}" for w in warnings]
    if not errors and not warnings:
        lines.append("- ✅ all checks passed")
    report = "\n".join(lines) + "\n"
    print(report)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write(report)

    if errors:
        sys.exit(1)
    if args.write_profile:
        Path(args.write_profile).write_text(json.dumps(profile(df, raw), indent=2) + "\n")
        print(f"profile written to {args.write_profile}")


if __name__ == "__main__":
    main()
