from datetime import date, timedelta
from functools import lru_cache

import numpy as np
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import integrity, inventory
from .config import settings
from .integrity import IntegrityError
from .metrics import model_integrity_ok, prediction_failures_total
from .ml.features import MIN_HISTORY_DAYS
from .ml.forecaster import Forecaster
from .models import ForecastLog, Product, Sale, StockBatch


@lru_cache(maxsize=1)
def _load_forecaster() -> Forecaster:
    if settings.require_model_manifest:
        try:
            integrity.verify(settings.model_path)
        except IntegrityError:
            model_integrity_ok.set(0)
            raise
    fc = Forecaster(settings.model_path)
    model_integrity_ok.set(1)
    return fc


def get_forecaster() -> Forecaster:
    try:
        return _load_forecaster()
    except FileNotFoundError as err:
        prediction_failures_total.labels(reason="model_missing").inc()
        raise HTTPException(503, "forecast model not available - run scripts/train_model.py") from err
    except IntegrityError as err:
        prediction_failures_total.labels(reason="integrity").inc()
        raise HTTPException(503, f"model refused: integrity check failed ({err})") from err


def daily_history(db: Session, product_id: int, end: date, days: int = 56) -> list[float]:
    start = end - timedelta(days=days - 1)
    rows = db.execute(
        select(Sale.sale_date, Sale.quantity)
        .where(Sale.product_id == product_id, Sale.sale_date >= start, Sale.sale_date <= end)
    ).all()
    by_day = {d: q for d, q in rows}
    return [float(by_day.get(start + timedelta(days=i), 0)) for i in range(days)]


def forecast_product(db: Session, fc: Forecaster, product: Product, days: int, today: date) -> list[dict]:
    history = daily_history(db, product.id, today - timedelta(days=1))
    if sum(1 for q in history[-MIN_HISTORY_DAYS:] if q > 0) < 7:
        prediction_failures_total.labels(reason="not_enough_history").inc()
        raise HTTPException(422, f"not enough sales history for {product.sku} to forecast")
    try:
        points = fc.forecast(history, today, days)
    except Exception:
        prediction_failures_total.labels(reason="model_error").inc()
        raise
    log_forecasts(db, product.id, today, points, fc.version)
    return points


def log_forecasts(db: Session, product_id: int, today: date, points: list[dict], version: str) -> None:
    targets = [date.fromisoformat(p["date"]) for p in points]
    existing = set(db.execute(
        select(ForecastLog.target_date, ForecastLog.horizon)
        .where(ForecastLog.product_id == product_id, ForecastLog.target_date.in_(targets))
    ).all())
    actuals = dict(db.execute(
        select(Sale.sale_date, Sale.quantity).where(Sale.product_id == product_id, Sale.sale_date.in_(targets))
    ).all())
    for p, target in zip(points, targets, strict=True):
        horizon = (target - today).days
        if (target, horizon) in existing:
            continue
        db.add(ForecastLog(product_id=product_id, target_date=target, horizon=horizon,
                           predicted_qty=p["predicted_qty"], model_version=version,
                           actual_qty=actuals.get(target)))
    db.commit()


def recommend_for_product(db: Session, fc: Forecaster, product: Product, today: date) -> dict:
    window = settings.forecast_window_days
    points = forecast_product(db, fc, product, window, today)
    daily = [p["predicted_qty"] for p in points]

    batches = db.scalars(select(StockBatch).where(StockBatch.product_id == product.id)).all()
    hist = daily_history(db, product.id, today - timedelta(days=1), days=28)
    rec = inventory.plan_order(
        daily,
        [inventory.Batch(b.quantity, b.expiry_date) for b in batches],
        product.lead_time_days,
        float(np.std(hist, ddof=1)),
        today,
        settings.service_level_z,
    )
    usable, waste = rec["usable_stock"], rec["expected_waste"]
    lead_demand, ss = rec["lead_time_demand"], rec["safety_stock"]

    if rec["action"] == "REORDER":
        reason = f"usable stock {usable} < lead-time demand {lead_demand:.0f} + safety {ss:.0f}"
        if waste:
            reason += f"; also {waste} units likely to expire"
    elif rec["action"] == "EXPIRY_RISK":
        reason = f"{waste} units expected to expire unsold in the next {window} days"
    else:
        reason = rec.get("note", "stock is in a healthy range")

    return {
        "product_id": product.id,
        "sku": product.sku,
        "name": product.name,
        "action": rec["action"],
        "qty": rec.get("qty", 0),
        "on_hand": rec["on_hand"],
        "usable_stock": usable,
        "expected_waste": waste,
        "forecast_demand": round(rec["forecast_demand"], 1),
        "lead_time_demand": round(lead_demand, 1),
        "safety_stock": round(ss, 1),
        "reason": reason,
    }


MAX_BACKFILL_DAYS = 60


def backfill_forecasts(db: Session, fc: Forecaster, product: Product, today: date, days: int) -> int:
    days = int(days)
    if not 1 <= days <= MAX_BACKFILL_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_BACKFILL_DAYS}, got {days}")
    added = 0
    for back in range(days, 0, -1):
        day = today - timedelta(days=back)
        history = daily_history(db, product.id, day - timedelta(days=1))
        if sum(1 for q in history[-MIN_HISTORY_DAYS:] if q > 0) < 7:
            continue
        before = db.scalar(select(ForecastLog.id).where(
            ForecastLog.product_id == product.id, ForecastLog.target_date == day, ForecastLog.horizon == 0))
        if before:
            continue
        log_forecasts(db, product.id, day, fc.forecast(history, day, 1), fc.version)
        added += 1
    return added
