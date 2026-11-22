from datetime import date, timedelta

import pytest

from app.inventory import Batch, expiry_status, recommend, safety_stock, simulate_fefo

TODAY = date(2026, 1, 10)


def d(n):
    return TODAY + timedelta(days=n)


class TestRecommend:
    def test_reorder_when_stock_below_lead_time_need(self):
        r = recommend(forecast_demand=70, usable_stock=10, lead_time_demand=20, safety_stock=5)
        assert r == {"action": "REORDER", "qty": 15}

    def test_reorder_qty_is_rounded_up(self):
        r = recommend(forecast_demand=70, usable_stock=10, lead_time_demand=20.2, safety_stock=0)
        assert r["qty"] == 11

    def test_expiry_risk_when_waste_expected(self):
        r = recommend(forecast_demand=30, usable_stock=40, lead_time_demand=10, safety_stock=5, expected_waste=12)
        assert r["action"] == "EXPIRY_RISK"
        assert r["excess"] == 12

    def test_reorder_beats_expiry_risk(self):
        r = recommend(forecast_demand=30, usable_stock=5, lead_time_demand=10, safety_stock=5, expected_waste=12)
        assert r["action"] == "REORDER"

    def test_ok(self):
        r = recommend(forecast_demand=30, usable_stock=30, lead_time_demand=10, safety_stock=5)
        assert r["action"] == "OK"
        assert r["qty"] == 0

    def test_exactly_at_reorder_point_is_ok(self):
        r = recommend(forecast_demand=100, usable_stock=15, lead_time_demand=10, safety_stock=5)
        assert r["action"] == "OK"


class TestFefo:
    def test_everything_sells(self):
        usable, waste = simulate_fefo([Batch(20, d(5))], [5] * 7, TODAY)
        assert (usable, waste) == (20, 0)

    def test_old_batch_expires_before_selling(self):
        usable, waste = simulate_fefo([Batch(30, d(1)), Batch(50, d(6))], [10] * 7, TODAY)
        assert waste == 10
        assert usable == 70

    def test_oldest_batch_sold_first(self):
        usable, waste = simulate_fefo([Batch(50, d(6)), Batch(20, d(1))], [10] * 7, TODAY)
        assert waste == 0

    def test_already_expired_stock_is_waste(self):
        _, waste = simulate_fefo([Batch(8, d(-1)), Batch(10, d(5))], [2] * 7, TODAY)
        assert waste == 8

    def test_can_sell_on_expiry_day(self):
        _, waste = simulate_fefo([Batch(10, TODAY)], [10], TODAY)
        assert waste == 0

    def test_empty_stock(self):
        assert simulate_fefo([], [5] * 7, TODAY) == (0, 0)


def test_safety_stock_grows_with_lead_time():
    assert safety_stock(4, 4) == pytest.approx(2 * safety_stock(4, 1))
    assert safety_stock(4, 0) == 0


@pytest.mark.parametrize("days,expected", [(-1, "expired"), (0, "expiring_soon"), (2, "expiring_soon"), (3, "fresh")])
def test_expiry_status(days, expected):
    assert expiry_status(d(days), TODAY) == expected
