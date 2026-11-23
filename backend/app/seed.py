import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .catalog import PRODUCTS
from .config import settings
from .models import Product, Sale, StockBatch

log = logging.getLogger(__name__)

STARTING_STOCK = {
    "MLK-001": (0.6, 0.4), "CRD-002": (4.0, 0.8), "PNR-003": (4.0, 0.3),
    "BRD-004": (0.8, 0.4), "BAN-005": (3.5, 0.75), "TOM-006": (1.5, 0.4),
    "SPN-007": (3.0, 0.3), "EGG-008": (6.0, 0.4),
}


def seed(db: Session) -> bool:
    if db.scalar(select(func.count()).select_from(Product)):
        return False

    today = date.today()
    products = {}
    for p in PRODUCTS:
        fields = {k: v for k, v in p.items() if k != "avg_daily_demand"}
        products[p["sku"]] = Product(**fields)
    db.add_all(products.values())
    db.flush()

    if settings.seed_data_path.exists():
        sales = pd.read_csv(settings.seed_data_path, parse_dates=["date"])
        gap = (pd.Timestamp(today - timedelta(days=1)) - sales["date"].max()).days
        shift = -(-gap // 7) * 7
        sales["date"] = sales["date"] + pd.Timedelta(days=shift)
        sales = sales[sales["date"] < pd.Timestamp(today)]
        sales = sales[sales["sku"].isin(products.keys())]

        db.execute(insert(Sale), [
            {
                "product_id": products[r.sku].id,
                "sale_date": r.date.date(),
                "quantity": int(r.quantity),
                "on_promo": bool(r.on_promo),
                "is_holiday": bool(r.is_holiday),
            }
            for r in sales.itertuples()
        ])
    else:
        log.warning("seed data %s not found, skipping sales history", settings.seed_data_path)

    for p in PRODUCTS:
        cover, older_share = STARTING_STOCK.get(p["sku"], (2.0, 0.4))
        total = round(p["avg_daily_demand"] * cover)
        older = round(total * older_share)
        prod = products[p["sku"]]
        db.add(StockBatch(product_id=prod.id, quantity=older,
                          received_date=today - timedelta(days=p["shelf_life_days"] - 1),
                          expiry_date=today + timedelta(days=1)))
        db.add(StockBatch(product_id=prod.id, quantity=total - older,
                          received_date=today,
                          expiry_date=today + timedelta(days=p["shelf_life_days"])))

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        log.info("database was seeded by another instance")
        return False
    log.info("seeded %d products", len(products))
    return True
