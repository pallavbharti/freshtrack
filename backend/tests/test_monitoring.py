from datetime import date

import numpy as np

from app.ml import drift


def test_psi_low_for_same_distribution():
    rng = np.random.default_rng(1)
    ref = drift.build_reference(rng.poisson(30, 90))
    assert drift.psi(ref, rng.poisson(30, 28)) < 0.25


def test_psi_high_for_shifted_distribution():
    rng = np.random.default_rng(1)
    ref = drift.build_reference(rng.poisson(30, 90))
    assert drift.psi(ref, rng.poisson(45, 28)) > 0.25


def test_psi_handles_empty_bins_without_blowing_up():
    ref = drift.build_reference(list(range(100)))
    value = drift.psi(ref, [5] * 28)
    assert np.isfinite(value)


def test_backfill_gives_closed_loop_history(client):
    r = client.post("/model/backfill?days=7")
    assert r.status_code == 200
    health = client.get("/model/health").json()
    assert health["products"]["MLK-001"]["eval_days"] >= 7
    store = health["store"]
    assert store["eval_days"] >= 7
    assert store["wape_7d"] < 1.45 * store["holdout_wape"]


def test_backfill_is_idempotent(client):
    client.post("/model/backfill?days=7")
    second = client.post("/model/backfill?days=7").json()
    assert sum(second["forecasts_added"].values()) == 0


def test_forecast_is_logged_once_per_day_and_horizon(client):
    client.get("/forecast/2?days=7")
    client.get("/forecast/2?days=7")
    from app.database import SessionLocal
    from app.models import ForecastLog

    with SessionLocal() as db:
        rows = db.query(ForecastLog).filter(ForecastLog.product_id == 2,
                                            ForecastLog.target_date >= date.today()).all()
    assert sorted(r.horizon for r in rows) == list(range(7))


def test_sale_closes_the_loop(client):
    from datetime import timedelta

    yesterday = date.today() - timedelta(days=1)
    client.post("/model/backfill?days=3")
    before = client.get("/model/health").json()["products"]["PNR-003"]

    client.post("/stock", json={"product_id": 3, "quantity": 500, "received_date": str(yesterday),
                                "expiry_date": str(date.today())})
    r = client.post("/sales", json={"product_id": 3, "sale_date": str(yesterday), "quantity": 60})
    assert r.status_code == 201

    after = client.get("/model/health").json()["products"]["PNR-003"]
    assert after["eval_days"] >= 1
    assert after["bias_7d"] < before["bias_7d"]


def test_todays_partial_sales_are_not_scored(client):
    client.get("/forecast/4?days=1")
    client.post("/stock", json={"product_id": 4, "quantity": 50, "received_date": str(date.today()),
                                "expiry_date": str(date.today())})
    client.post("/sales", json={"product_id": 4, "sale_date": str(date.today()), "quantity": 1})
    from app.database import SessionLocal
    from app.monitoring import model_health
    from app.services import _load_forecaster

    with SessionLocal() as db:
        h = model_health(db, _load_forecaster().metrics, date.today())
    assert h["products"]["BRD-004"]["wape_7d"] is None or h["products"]["BRD-004"]["wape_7d"] < 60


def test_model_health_reports_drift_for_every_product(client):
    health = client.get("/model/health").json()
    assert health["store_psi"] >= 0
    from app.catalog import PRODUCTS

    for p in PRODUCTS:
        assert health["products"][p["sku"]]["psi"] is not None, p["sku"]


def test_metrics_expose_closed_loop_gauges(client):
    body = client.get("/metrics").text
    for name in ("forecast_wape_7d", "forecast_bias_7d", "data_drift_psi", "data_drift_psi_store",
                 "forecast_holdout_wape", "forecast_wape_7d_store", "forecast_holdout_wape_store"):
        assert name in body, name


def test_export_matches_training_format(client):
    r = client.get("/sales/export?days=90")
    assert r.status_code == 200
    lines = r.text.strip().splitlines()
    assert lines[0] == "date,sku,quantity,on_promo,is_holiday"
    assert len(lines) > 8 * 60


def test_invalidate_works_right_after_boot(monkeypatch):
    import app.monitoring as m

    calls = []
    c = m.ModelHealthCollector(get_metrics=lambda: {}, ttl=30.0)
    monkeypatch.setattr(m, "model_health", lambda db, metrics, today: calls.append(1) or {"n": len(calls)})
    monkeypatch.setattr(m.time, "monotonic", lambda: 5.0)
    assert c._health() == {"n": 1}
    c.invalidate()
    assert c._health() == {"n": 2}
