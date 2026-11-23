import copy
import json
from pathlib import Path

import pytest
import yaml

from scripts.policy_gate import DEFAULT_CONFIG, evaluate, markdown

CONFIG = yaml.safe_load(Path(DEFAULT_CONFIG).read_text())


def kpis(waste=0.27, fill=99.5, stockouts=4, wape=15.4, base_waste=0.24, base_fill=99.5, rep_fill=93.0):
    return {
        "forecast_wape": wape,
        "data": {"sha256": "abc"},
        "policies": {
            "replenish": {"waste_rate": 0.0, "fill_rate": rep_fill, "stockout_days": 90, "lost_sales": 900},
            "baseline": {"waste_rate": base_waste, "fill_rate": base_fill, "stockout_days": 4, "lost_sales": 60},
            "ours": {"waste_rate": waste, "fill_rate": fill, "stockout_days": stockouts, "lost_sales": 60},
        },
    }


def failed(checks):
    return {c.name for c in checks if not c.passed}


def test_identical_kpis_pass():
    ref = kpis()
    assert failed(evaluate(copy.deepcopy(ref), ref, CONFIG)) == set()


def test_waste_regression_fails():
    checks = evaluate(kpis(waste=0.5), kpis(), CONFIG)
    assert "waste_rate vs main" in failed(checks)


def test_small_waste_change_within_tolerance_passes():
    checks = evaluate(kpis(waste=0.30), kpis(waste=0.27), CONFIG)
    assert "waste_rate vs main" not in failed(checks)


def test_fill_rate_drop_fails():
    checks = evaluate(kpis(fill=99.0), kpis(fill=99.5), CONFIG)
    assert "fill_rate vs main" in failed(checks)


def test_stockout_increase_fails():
    checks = evaluate(kpis(stockouts=10), kpis(stockouts=4), CONFIG)
    assert "stockout_days vs main" in failed(checks)


def test_forecast_wape_regression_fails():
    checks = evaluate(kpis(wape=19.0), kpis(wape=15.0), CONFIG)
    assert "forecast WAPE vs main" in failed(checks)


def test_ours_worse_than_baseline_policy_fails():
    checks = evaluate(kpis(waste=0.6, base_waste=0.24), None, CONFIG)
    assert "ours vs baseline policy: waste" in failed(checks)


def test_ours_must_beat_replenish():
    checks = evaluate(kpis(fill=94.0, base_fill=94.0, rep_fill=93.5), None, CONFIG)
    assert "ours vs replenish policy: fill gain" in failed(checks)


def test_improvement_passes():
    checks = evaluate(kpis(waste=0.1, fill=99.8), kpis(), CONFIG)
    assert failed(checks) == set()


def test_without_reference_only_comparison_checks_run():
    names = {c.name for c in evaluate(kpis(), None, CONFIG)}
    assert not any("vs main" in n for n in names)
    assert "ours vs baseline policy: waste" in names


@pytest.mark.parametrize("bad", [{"waste": 5.0}, {"fill": 90.0, "base_fill": 90.0, "rep_fill": 80.0}])
def test_absolute_limits(bad):
    assert any("absolute" in n for n in failed(evaluate(kpis(**bad), None, CONFIG)))


def test_markdown_report_mentions_synthetic_data_and_result():
    md = markdown(kpis(waste=0.5), kpis(), evaluate(kpis(waste=0.5), kpis(), CONFIG))
    assert "FAILED" in md
    assert "synthetic" in md


def test_committed_reference_is_valid():
    ref = json.loads((Path(DEFAULT_CONFIG).parent.parent / "results" / "baseline_kpis.json").read_text())
    assert set(ref["policies"]) == {"replenish", "baseline", "ours"}
    assert "synthetic" in ref["note"].lower()
