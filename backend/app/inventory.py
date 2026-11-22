import math
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class Batch:
    quantity: int
    expiry_date: date


def simulate_fefo(batches: list[Batch], daily_demand: list[float], today: date) -> tuple[int, int]:
    stock = sorted(([b.expiry_date, b.quantity] for b in batches if b.quantity > 0), key=lambda x: x[0])
    on_hand = sum(q for _, q in stock)
    waste = 0.0

    for i, demand in enumerate(daily_demand):
        day = today + timedelta(days=i)

        while stock and stock[0][0] < day:
            waste += stock.pop(0)[1]

        left = demand
        while left > 0 and stock:
            take = min(left, stock[0][1])
            stock[0][1] -= take
            left -= take
            if stock[0][1] <= 0:
                stock.pop(0)

    waste = int(round(waste))
    return on_hand - waste, waste


def safety_stock(daily_std: float, lead_time_days: int, z: float = 1.65) -> float:
    if lead_time_days <= 0:
        return 0.0
    return z * daily_std * math.sqrt(lead_time_days)


def recommend(forecast_demand: float, usable_stock: float, lead_time_demand: float,
              safety_stock: float, expected_waste: float = 0) -> dict:
    need = lead_time_demand + safety_stock - usable_stock
    if need > 0:
        return {"action": "REORDER", "qty": math.ceil(need)}
    if expected_waste > 0:
        return {"action": "EXPIRY_RISK", "qty": 0, "excess": round(expected_waste)}
    if usable_stock > forecast_demand + safety_stock:
        return {"action": "OK", "qty": 0, "note": "stock above forecast window demand"}
    return {"action": "OK", "qty": 0}


def plan_order(daily_forecast: list[float], batches: list[Batch], lead_time_days: int,
               demand_std: float, today: date, z: float = 1.65) -> dict:
    window = len(daily_forecast)
    usable, waste = simulate_fefo(batches, daily_forecast, today)
    cover = min(lead_time_days + 1, window)
    lead_demand = sum(daily_forecast[:cover])
    ss = safety_stock(demand_std, cover, z)
    forecast_total = sum(daily_forecast)

    rec = recommend(forecast_total, usable, lead_demand, ss, waste)
    rec.update(
        usable_stock=usable,
        expected_waste=waste,
        on_hand=sum(b.quantity for b in batches),
        lead_time_demand=lead_demand,
        safety_stock=ss,
        forecast_demand=forecast_total,
    )
    return rec


def expiry_status(expiry: date, today: date, soon_days: int = 2) -> str:
    left = (expiry - today).days
    if left < 0:
        return "expired"
    if left <= soon_days:
        return "expiring_soon"
    return "fresh"
