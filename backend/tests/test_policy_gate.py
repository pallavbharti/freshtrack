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


def run_main(monkeypatch, *args):
    import sys

    from scripts import policy_gate

    monkeypatch.setattr(sys, "argv", ["policy_gate.py", *map(str, args)])
    try:
        policy_gate.main()
    except SystemExit as e:
        return e.code or 0
    return 0


def write(path, data):
    path.write_text(json.dumps(data))
    return path


def test_main_passes_and_writes_outputs(tmp_path, monkeypatch):
    cand = write(tmp_path / "cand.json", kpis())
    ref = write(tmp_path / "ref.json", kpis())
    out, summary = tmp_path / "out" / "result.json", tmp_path / "summary.md"
    code = run_main(monkeypatch, "--candidate", cand, "--baseline", ref, "--out", out, "--summary", summary)
    assert code == 0
    assert json.loads(out.read_text())["gate"]["passed"] is True
    assert "PASSED" in summary.read_text()


def test_main_fails_on_regression(tmp_path, monkeypatch):
    cand = write(tmp_path / "cand.json", kpis(waste=0.9))
    ref = write(tmp_path / "ref.json", kpis())
    assert run_main(monkeypatch, "--candidate", cand, "--baseline", ref) == 1


def test_main_without_reference_runs_comparison_checks(tmp_path, monkeypatch, capsys):
    cand = write(tmp_path / "cand.json", kpis())
    assert run_main(monkeypatch, "--candidate", cand, "--baseline", tmp_path / "missing.json") == 0
    assert "no reference" in capsys.readouterr().out


def test_write_baseline_only_when_gate_passes(tmp_path, monkeypatch):
    cand = write(tmp_path / "cand.json", kpis(waste=0.9))
    ref = write(tmp_path / "ref.json", kpis())
    before = ref.read_text()
    assert run_main(monkeypatch, "--candidate", cand, "--baseline", ref, "--write-baseline") == 1
    assert ref.read_text() == before


def test_write_baseline_with_accepted_regression_records_reason(tmp_path, monkeypatch):
    cand = write(tmp_path / "cand.json", kpis(waste=0.9))
    ref = write(tmp_path / "ref.json", kpis())
    code = run_main(monkeypatch, "--candidate", cand, "--baseline", ref, "--write-baseline",
                    "--accept-regression", "new supplier, reviewed in PR")
    assert code == 0
    saved = json.loads(ref.read_text())
    assert saved["accepted"] == {**saved["accepted"], "gate_passed": False, "reason": "new supplier, reviewed in PR"}
    assert saved["policies"]["ours"]["waste_rate"] == 0.9


def test_write_baseline_when_gate_passes(tmp_path, monkeypatch):
    cand = write(tmp_path / "cand.json", kpis(waste=0.1, fill=99.8))
    ref = tmp_path / "new" / "ref.json"
    assert run_main(monkeypatch, "--candidate", cand, "--baseline", ref, "--write-baseline") == 0
    assert json.loads(ref.read_text())["accepted"]["reason"] == "gate passed"


def test_dataset_change_is_flagged_in_report():
    other = kpis()
    other["data"] = {"sha256": "different"}
    md = markdown(other, kpis(), evaluate(other, kpis(), CONFIG))
    assert "dataset differs" in md
