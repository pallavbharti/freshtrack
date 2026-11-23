from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import monitoring
from ..auth import require_manager, require_viewer
from ..database import get_db
from ..models import Product, Sale, StockBatch
from ..schemas import SaleIn, SaleOut

router = APIRouter(prefix="/sales", tags=["sales"], dependencies=[Depends(require_viewer)])


@router.get("/export", response_class=PlainTextResponse, dependencies=[Depends(require_manager)])
def export_sales(days: int = Query(730, ge=60, le=3650), db: Session = Depends(get_db)):
    since = date.today() - timedelta(days=days)
    rows = db.execute(
        select(Sale.sale_date, Product.sku, Sale.quantity, Sale.on_promo, Sale.is_holiday)
        .join(Product, Product.id == Sale.product_id)
        .where(Sale.sale_date >= since, Sale.sale_date < date.today())
        .order_by(Product.sku, Sale.sale_date)
    ).all()
    lines = ["date,sku,quantity,on_promo,is_holiday"]
    lines += [f"{d.isoformat()},{sku},{q},{int(promo)},{int(hol)}" for d, sku, q, promo, hol in rows]
    return "\n".join(lines) + "\n"


@router.get("", response_model=list[SaleOut])
def list_sales(product_id: int, days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    since = date.today() - timedelta(days=days)
    q = (
        select(Sale)
        .where(Sale.product_id == product_id, Sale.sale_date >= since)
        .order_by(Sale.sale_date)
    )
    return db.scalars(q).all()


@router.post("", response_model=SaleOut, status_code=201, dependencies=[Depends(require_manager)])
def record_sale(body: SaleIn, db: Session = Depends(get_db)):
    if not db.get(Product, body.product_id):
        raise HTTPException(404, "product not found")

    batches = db.scalars(
        select(StockBatch)
        .where(StockBatch.product_id == body.product_id, StockBatch.expiry_date >= body.sale_date)
        .order_by(StockBatch.expiry_date)
    ).all()
    available = sum(b.quantity for b in batches)
    if body.quantity > available:
        raise HTTPException(409, f"only {available} units in stock")

    left = body.quantity
    for b in batches:
        if left == 0:
            break
        take = min(left, b.quantity)
        b.quantity -= take
        left -= take
        if b.quantity == 0:
            db.delete(b)

    sale = db.scalar(select(Sale).where(Sale.product_id == body.product_id, Sale.sale_date == body.sale_date))
    if sale:
        sale.quantity += body.quantity
        sale.on_promo = sale.on_promo or body.on_promo
    else:
        sale = Sale(**body.model_dump())
        db.add(sale)

    db.flush()
    monitoring.record_actual(db, body.product_id, body.sale_date, sale.quantity)
    db.commit()
    monitoring.collector.invalidate()
    db.refresh(sale)
    return sale
