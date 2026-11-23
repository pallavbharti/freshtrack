import json
from pathlib import Path

import pytest

from scripts.validate_data import profile, validate

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def clean():
    import pandas as pd

    return pd.read_csv(DATA / "sales.csv")


@pytest.fixture(scope="module")
def ref(clean):
    return profile(clean, (DATA / "sales.csv").read_bytes())


def test_committed_dataset_matches_committed_profile(clean):
    committed = json.loads((DATA / "profile.json").read_text())
    errors, _ = validate(clean, committed)
    assert errors == []
    assert committed["sha256"] == profile(clean, (DATA / "sales.csv").read_bytes())["sha256"]


def test_clean_data_passes(clean, ref):
    errors, warnings = validate(clean, ref)
    assert errors == [] and warnings == []


def test_poisoned_x10_fails(clean, ref):
    bad = clean.copy()
    m = (bad.sku == "MLK-001") & (bad.date >= "2026-05-01")
    bad.loc[m, "quantity"] *= 10
    errors, _ = validate(bad, ref)
    assert any("MLK-001" in e for e in errors)


def test_negative_quantity_fails(clean, ref):
    bad = clean.copy()
    bad.loc[bad.index[-1], "quantity"] = -4
    assert any("negative" in e for e in validate(bad, ref)[0])


def test_duplicates_fail(clean, ref):
    import pandas as pd

    bad = pd.concat([clean, clean.tail(10)])
    assert any("duplicate" in e for e in validate(bad, ref)[0])


def test_schema_change_fails(clean, ref):
    bad = clean.rename(columns={"quantity": "qty"})
    assert any("columns" in e for e in validate(bad, ref)[0])


def test_bad_flags_fail(clean, ref):
    bad = clean.copy()
    bad.loc[bad.index[0], "on_promo"] = 7
    assert any("on_promo" in e for e in validate(bad, ref)[0])


def test_truncated_dataset_fails(clean, ref):
    bad = clean[clean.date >= "2026-03-01"]
    errors = validate(bad, ref)[0]
    assert any("rows" in e for e in errors)


def test_mean_collapse_fails(clean, ref):
    bad = clean.copy()
    m = (bad.sku == "TOM-006") & (bad.date >= "2026-04-01")
    bad.loc[m, "quantity"] = 0
    assert any("TOM-006" in e for e in validate(bad, ref)[0])


def test_real_demand_shift_is_allowed(clean, ref):
    shifted = clean.copy()
    m = shifted.date >= "2026-06-03"
    shifted.loc[m, "quantity"] = (shifted.loc[m, "quantity"] * 1.4).round().astype(int)
    assert validate(shifted, ref)[0] == []


def test_new_product_is_a_warning_not_an_error(clean, ref):
    import pandas as pd

    extra = clean[clean.sku == "MLK-001"].assign(sku="NEW-999")
    errors, warnings = validate(pd.concat([clean, extra]), ref)
    assert errors == []
    assert any("NEW-999" in w for w in warnings)
