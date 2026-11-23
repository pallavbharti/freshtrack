from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    category: str
    shelf_life_days: int = Field(gt=0)
    lead_time_days: int = Field(default=1, ge=0)
    unit_price: float = Field(default=0, ge=0)


class ProductOut(ProductIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class StockIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    received_date: date
    expiry_date: date

    @model_validator(mode="after")
    def expiry_after_received(self):
        if self.expiry_date < self.received_date:
            raise ValueError("expiry_date cannot be before received_date")
        return self


class StockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    product_name: str
    quantity: int
    received_date: date
    expiry_date: date
    days_to_expiry: int
    status: Literal["fresh", "expiring_soon", "expired"]


class SaleIn(BaseModel):
    product_id: int
    sale_date: date
    quantity: int = Field(ge=0)
    on_promo: bool = False
    is_holiday: bool = False


class SaleOut(SaleIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ForecastPoint(BaseModel):
    date: date
    predicted_qty: float


class ForecastOut(BaseModel):
    product_id: int
    sku: str
    days: int
    total_predicted: float
    points: list[ForecastPoint]


class Recommendation(BaseModel):
    product_id: int
    sku: str
    name: str
    action: Literal["REORDER", "EXPIRY_RISK", "OK"]
    qty: int = 0
    on_hand: int
    usable_stock: int
    expected_waste: int
    forecast_demand: float
    lead_time_demand: float
    safety_stock: float
    reason: str
