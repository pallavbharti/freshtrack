import logging
import statistics
import time
from datetime import date, timedelta

from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .ml import drift
from .models import ForecastLog, Product, Sale

log = logging.getLogger(__name__)

EVAL_DAYS = 7


def record_actual(db: Session, product_id: int, day: date, total_qty: int) -> None:
    rows = db.scalars(
        select(ForecastLog).where(ForecastLog.product_id == product_id, ForecastLog.target_date == day)
    ).all()
    for row in rows:
        row.actual_qty = total_qty


def model_health(db: Session, metrics: dict, today: date) -> dict:
    reference = metrics.get("reference_distribution", {})
    holdout = metrics.get("holdout_wape_by_sku", {})
    products = db.scalars(select(Product).order_by(Product.id)).all()

    out = {"products": {}, "store_psi": 0.0}
    psis = []
    store_err = store_pred = store_actual = 0.0
    store_days = set()
    for p in products:
        rows = db.execute(
            select(ForecastLog.predicted_qty, ForecastLog.actual_qty, ForecastLog.target_date)
            .where(ForecastLog.product_id == p.id, ForecastLog.horizon == 0,
                   ForecastLog.actual_qty.is_not(None),
                   ForecastLog.target_date < today)
            .order_by(ForecastLog.target_date.desc())
            .limit(EVAL_DAYS)
        ).all()
        pred = sum(r[0] for r in rows)
        actual = sum(r[1] for r in rows)
        abs_err = sum(abs(r[0] - r[1]) for r in rows)
        store_err += abs_err
        store_pred += pred
        store_actual += actual
        store_days.update(r[2] for r in rows)

        entry = {
            "eval_days": len(rows),
            "wape_7d": round(100 * abs_err / actual, 2) if actual else None,
            "bias_7d": round(100 * (pred - actual) / actual, 2) if actual else None,
            "holdout_wape": holdout.get(p.sku),
            "psi": None,
        }

        if p.sku in reference:
            start = today - timedelta(days=drift.RECENT_DAYS)
            recent = db.scalars(
                select(Sale.quantity).where(Sale.product_id == p.id, Sale.sale_date >= start, Sale.sale_date < today)
            ).all()
            if len(recent) >= drift.RECENT_DAYS // 2:
                entry["psi"] = round(drift.psi(reference[p.sku], recent), 4)
                psis.append(entry["psi"])

        out["products"][p.sku] = entry

    out["store_psi"] = round(statistics.median(psis), 4) if psis else 0.0
    out["store"] = {
        "eval_days": len(store_days),
        "wape_7d": round(100 * store_err / store_actual, 2) if store_actual else None,
        "bias_7d": round(100 * (store_pred - store_actual) / store_actual, 2) if store_actual else None,
        "holdout_wape": metrics.get("model_as_served", metrics.get("model", {})).get("wape"),
    }
    return out


class ModelHealthCollector:
    def __init__(self, get_metrics=None, ttl: float = 30.0):
        self.get_metrics = get_metrics
        self._ttl = ttl
        self._cache = None
        self._cached_at = 0.0

    def invalidate(self):
        self._cache = None

    def _health(self):
        if self._cache is None or time.monotonic() - self._cached_at > self._ttl:
            metrics = self.get_metrics() if self.get_metrics else None
            if metrics is None:
                return None
            with SessionLocal() as db:
                self._cache = model_health(db, metrics, date.today())
            self._cached_at = time.monotonic()
        return self._cache

    def describe(self):
        for name in ("forecast_wape_7d", "forecast_bias_7d", "forecast_eval_days", "forecast_holdout_wape",
                     "data_drift_psi", "data_drift_psi_store", "forecast_eval_days_store",
                     "forecast_wape_7d_store", "forecast_bias_7d_store", "forecast_holdout_wape_store"):
            yield GaugeMetricFamily(name, name)

    def collect(self):
        try:
            health = self._health()
        except Exception:
            log.exception("model health computation failed")
            return
        if not health:
            return

        wape = GaugeMetricFamily("forecast_wape_7d", "Live WAPE over the last 7 evaluated days (%)", labels=["sku"])
        bias = GaugeMetricFamily("forecast_bias_7d", "Forecast bias over the last 7 evaluated days (%)", labels=["sku"])
        days = GaugeMetricFamily("forecast_eval_days", "Days with both a forecast and actual sales", labels=["sku"])
        hold = GaugeMetricFamily("forecast_holdout_wape", "WAPE on the held-out test set at training (%)",
                                 labels=["sku"])
        psi = GaugeMetricFamily("data_drift_psi", "PSI of last 28 days of sales vs training data", labels=["sku"])

        for sku, e in health["products"].items():
            days.add_metric([sku], e["eval_days"])
            if e["wape_7d"] is not None:
                wape.add_metric([sku], e["wape_7d"])
                bias.add_metric([sku], e["bias_7d"])
            if e["holdout_wape"] is not None:
                hold.add_metric([sku], e["holdout_wape"])
            if e["psi"] is not None:
                psi.add_metric([sku], e["psi"])

        yield from (wape, bias, days, hold, psi)

        st = health["store"]
        yield GaugeMetricFamily("forecast_eval_days_store", "Distinct days evaluated (store)", value=st["eval_days"])
        if st["wape_7d"] is not None:
            yield GaugeMetricFamily("forecast_wape_7d_store", "Live WAPE, all products (%)", value=st["wape_7d"])
            yield GaugeMetricFamily("forecast_bias_7d_store", "Forecast bias, all products (%)", value=st["bias_7d"])
        if st["holdout_wape"] is not None:
            yield GaugeMetricFamily("forecast_holdout_wape_store", "Held-out WAPE at training, all products (%)",
                                    value=st["holdout_wape"])
        yield GaugeMetricFamily("data_drift_psi_store", "Median PSI across products", value=health["store_psi"])


collector = ModelHealthCollector()
