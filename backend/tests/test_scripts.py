import json
import sys

import pytest

from scripts import check_model, simulate, train_model


@pytest.fixture(scope="module")
def report(sales_df):
    return simulate.build_report(sales_df, "fixture")


def test_simulation_accounts_for_every_unit(report):
    df, _ = report
    assert set(df["policy"]) == set(simulate.POLICIES)
    assert len(df) == len(simulate.PRODUCTS) * len(simulate.POLICIES)
    assert (df["sold"] + df["lost_sales"] == df["demand"]).all()
    assert (df["sold"] + df["expired"] <= df["received"]).all()
    assert df["fill_rate_pct"].between(0, 100).all()
    assert df["waste_rate_pct"].between(0, 100).all()


def test_report_records_data_and_marks_it_synthetic(report, sales_df):
    _, rep = report
    assert "synthetic" in rep["note"].lower()
    assert rep["data"]["rows"] == len(sales_df)
    assert len(rep["data"]["sha256"]) == 64
    assert rep["test_days"] == simulate.TEST_DAYS
    for policy in simulate.POLICIES:
        assert set(rep["policies"][policy]) >= {"waste_rate", "fill_rate", "stockout_days"}


def test_forecast_policy_beats_plain_replenishment(report):
    _, rep = report
    assert rep["policies"]["ours"]["fill_rate"] > rep["policies"]["replenish"]["fill_rate"]


def test_simulate_cli_writes_outputs(tmp_path, monkeypatch, capsys, sales_df):
    data = tmp_path / "sales.csv"
    sales_df.to_csv(data, index=False)
    out, kpi = tmp_path / "out" / "per_product.csv", tmp_path / "out" / "kpis.json"
    monkeypatch.setattr(sys, "argv", ["simulate.py", "--data", str(data), "--out", str(out), "--json", str(kpi)])
    simulate.main()
    assert out.exists()
    assert json.loads(kpi.read_text())["data"]["source"] == str(data)
    printed = capsys.readouterr().out
    assert "Totals (simulated on synthetic data)" in printed
    assert "KPI JSON written" in printed


def test_simulate_cli_quiet_prints_only_totals(tmp_path, monkeypatch, capsys, sales_df):
    data = tmp_path / "sales.csv"
    sales_df.to_csv(data, index=False)
    monkeypatch.setattr(sys, "argv", ["simulate.py", "--data", str(data), "--quiet"])
    simulate.main()
    printed = capsys.readouterr().out
    assert printed.startswith("Totals")


def test_load_or_generate_prefers_explicit_path(tmp_path, sales_df):
    data = tmp_path / "s.csv"
    sales_df.head(10).to_csv(data, index=False)
    df, source = simulate.load_or_generate(str(data))
    assert len(df) == 10 and source == str(data)


def test_train_model_cli_saves_model_and_metrics(tmp_path, monkeypatch, capsys, sales_df):
    data, out = tmp_path / "sales.csv", tmp_path / "m" / "model.joblib"
    sales_df.to_csv(data, index=False)
    monkeypatch.setattr(sys, "argv", ["train_model.py", "--data", str(data), "--out", str(out)])
    train_model.main()
    assert out.exists()
    assert out.with_suffix(".metrics.json").exists()
    assert "model saved to" in capsys.readouterr().out


def _metrics(model, naive):
    return {"model": {"wape": model}, "naive_lag7": {"wape": naive}}


def test_check_model_passes_good_model():
    assert check_model.check(_metrics(15.0, 25.0)) == []


def test_check_model_flags_limit_and_naive():
    problems = check_model.check(_metrics(30.0, 25.0))
    assert len(problems) == 2


@pytest.mark.parametrize(("wape", "code"), [(15.0, 0), (30.0, 1)])
def test_check_model_cli_exit_code(tmp_path, monkeypatch, wape, code):
    monkeypatch.setattr(check_model, "MODELS_DIR", tmp_path.resolve())
    (tmp_path / "m.metrics.json").write_text(json.dumps(_metrics(wape, 25.0)))
    monkeypatch.setattr(sys, "argv", ["check_model.py", "m.metrics.json"])
    with pytest.raises(SystemExit) as exc:
        check_model.main()
    assert exc.value.code == code
