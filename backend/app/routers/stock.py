from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..auth import require_manager, require_viewer
from ..database import get_db
from ..inventory import expiry_status
from ..models import Product, StockBatch
from ..schemas import StockIn, StockOut

router = APIRouter(prefix="/stock", tags=["stock"], dependencies=[Depends(require_viewer)])


def _to_out(b: StockBatch, today: date) -> StockOut:
    return StockOut(
        id=b.id,
        product_id=b.product_id,
        product_name=b.product.name,
        quantity=b.quantity,
        received_date=b.received_date,
        expiry_date=b.expiry_date,
        days_to_expiry=(b.expiry_date - today).days,
        status=expiry_status(b.expiry_date, today),
    )


@router.get("", response_model=list[StockOut])
def list_stock(product_id: int | None = None, db: Session = Depends(get_db)):
    q = select(StockBatch).options(joinedload(StockBatch.product)).order_by(StockBatch.expiry_date)
    if product_id is not None:
        q = q.where(StockBatch.product_id == product_id)
    today = date.today()
    return [_to_out(b, today) for b in db.scalars(q).all()]


@router.post("", response_model=StockOut, status_code=201, dependencies=[Depends(require_manager)])
def add_stock(body: StockIn, db: Session = Depends(get_db)):
    if not db.get(Product, body.product_id):
        raise HTTPException(404, "product not found")
    batch = StockBatch(**body.model_dump())
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return _to_out(batch, date.today())


@router.delete("/{batch_id}", status_code=204, dependencies=[Depends(require_manager)])
def remove_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(StockBatch, batch_id)
    if not batch:
        raise HTTPException(404, "batch not found")
    db.delete(batch)
    db.commit()
