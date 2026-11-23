from datetime import date, timedelta


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready(client):
    assert client.get("/ready").status_code == 200


def test_products_seeded(client):
    r = client.get("/products")
    assert r.status_code == 200
    assert len(r.json()) == 8


def test_unknown_product_404(client):
    assert client.get("/products/9999").status_code == 404


def test_create_product_and_duplicate_sku(client):
    body = {"sku": "TST-100", "name": "Test Item", "category": "Test", "shelf_life_days": 3}
    assert client.post("/products", json=body).status_code == 201
    assert client.post("/products", json=body).status_code == 409


def test_invalid_product_rejected(client):
    body = {"sku": "BAD-1", "name": "x", "category": "x", "shelf_life_days": 0}
    assert client.post("/products", json=body).status_code == 422


def test_stock_list_has_expiry_status(client):
    rows = client.get("/stock").json()
    assert rows
    assert {"days_to_expiry", "status"} <= rows[0].keys()
    days = [r["days_to_expiry"] for r in rows]
    assert days == sorted(days)


def test_stock_expiry_before_received_rejected(client):
    today = date.today()
    body = {"product_id": 1, "quantity": 5, "received_date": str(today),
            "expiry_date": str(today - timedelta(days=1))}
    assert client.post("/stock", json=body).status_code == 422


def test_sale_reduces_stock_oldest_first(client):
    before = [b for b in client.get("/stock?product_id=8").json()]
    oldest = before[0]
    r = client.post("/sales", json={"product_id": 8, "sale_date": str(date.today()), "quantity": 2})
    assert r.status_code == 201
    after = {b["id"]: b for b in client.get("/stock?product_id=8").json()}
    assert after[oldest["id"]]["quantity"] == oldest["quantity"] - 2


def test_cannot_sell_more_than_stock(client):
    r = client.post("/sales", json={"product_id": 1, "sale_date": str(date.today()), "quantity": 100000})
    assert r.status_code == 409


def test_forecast(client):
    r = client.get("/forecast/1?days=7")
    assert r.status_code == 200
    data = r.json()
    assert len(data["points"]) == 7
    assert all(p["predicted_qty"] >= 0 for p in data["points"])


def test_forecast_without_history_is_422(client):
    new = client.post("/products", json={"sku": "NEW-1", "name": "New", "category": "x", "shelf_life_days": 2})
    r = client.get(f"/forecast/{new.json()['id']}")
    assert r.status_code == 422


def test_recommendations(client):
    r = client.get("/recommendations")
    assert r.status_code == 200
    recs = r.json()
    assert len(recs) >= 8
    assert {x["action"] for x in recs} <= {"REORDER", "EXPIRY_RISK", "OK"}
    for x in recs:
        if x["action"] == "REORDER":
            assert x["qty"] > 0


def test_metrics_endpoint(client):
    client.get("/recommendations")
    body = client.get("/metrics").text
    assert "http_requests_total" in body
    assert "inventory_recommendations" in body
    assert "prediction_failures_total" in body


def test_seed_keeps_weekdays_aligned(client):
    import os

    import pandas as pd

    from app.database import SessionLocal
    from app.models import Sale

    csv_first = pd.to_datetime(pd.read_csv(os.environ["SEED_DATA_PATH"])["date"]).min().date()
    with SessionLocal() as db:
        db_first = min(s.sale_date for s in db.query(Sale).filter(Sale.product_id == 1))
        db_last = max(s.sale_date for s in db.query(Sale).filter(Sale.product_id == 1))
    assert (db_first - csv_first).days % 7 == 0
    assert db_last < date.today()
