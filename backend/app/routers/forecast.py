from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import monitoring
from ..auth import require_manager, require_viewer
from ..database import get_db
from ..metrics import expected_waste_units, predictions_total, recommendations_by_action
from ..ml.forecaster import Forecaster
from ..models import Product
from ..schemas import ForecastOut, Recommendation
from ..services import backfill_forecasts, forecast_product, get_forecaster, recommend_for_product

router = APIRouter(tags=["forecast"], dependencies=[Depends(require_viewer)])


@router.get("/forecast/{product_id}", response_model=ForecastOut)
def forecast(product_id: int, days: int = Query(7, ge=1, le=30),
             db: Session = Depends(get_db), fc: Forecaster = Depends(get_forecaster)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "product not found")

    points = forecast_product(db, fc, product, days, date.today())
    predictions_total.labels(endpoint="forecast").inc()
    return {
        "product_id": product.id,
        "sku": product.sku,
        "days": days,
        "total_predicted": round(sum(p["predicted_qty"] for p in points), 1),
        "points": points,
    }


@router.get("/recommendations", response_model=list[Recommendation])
def recommendations(db: Session = Depends(get_db), fc: Forecaster = Depends(get_forecaster)):
    today = date.today()
    out = []
    for product in db.scalars(select(Product).order_by(Product.id)).all():
        try:
            out.append(recommend_for_product(db, fc, product, today))
        except HTTPException as e:
            if e.status_code != 422:
                raise

    predictions_total.labels(endpoint="recommendations").inc()
    for action in ("REORDER", "EXPIRY_RISK", "OK"):
        recommendations_by_action.labels(action=action).set(sum(r["action"] == action for r in out))
    expected_waste_units.set(sum(r["expected_waste"] for r in out))
    return out


@router.get("/model/health")
def model_health(db: Session = Depends(get_db), fc: Forecaster = Depends(get_forecaster)):
    return monitoring.model_health(db, fc.metrics, date.today())


@router.post("/model/backfill", dependencies=[Depends(require_manager)])
def model_backfill(days: int = Query(14, ge=1, le=60),
                   db: Session = Depends(get_db), fc: Forecaster = Depends(get_forecaster)):
    today = date.today()
    added = {p.sku: backfill_forecasts(db, fc, p, today, days)
             for p in db.scalars(select(Product).order_by(Product.id)).all()}
    monitoring.collector.invalidate()
    return {"days": days, "forecasts_added": added}


@router.get("/model/info")
def model_info(fc: Forecaster = Depends(get_forecaster)):
    m = {k: v for k, v in fc.metrics.items() if k != "reference_distribution"}
    return {"version": fc.version, "features": fc.features, "metrics": m}
