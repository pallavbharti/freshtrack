from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_manager, require_viewer
from ..database import get_db
from ..models import Product
from ..schemas import ProductIn, ProductOut

router = APIRouter(prefix="/products", tags=["products"], dependencies=[Depends(require_viewer)])


@router.get("", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.scalars(select(Product).order_by(Product.id)).all()


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "product not found")
    return product


@router.post("", response_model=ProductOut, status_code=201, dependencies=[Depends(require_manager)])
def create_product(body: ProductIn, db: Session = Depends(get_db)):
    if db.scalar(select(Product).where(Product.sku == body.sku)):
        raise HTTPException(409, f"sku {body.sku} already exists")
    product = Product(**body.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product
