import shutil
from pathlib import Path

import pytest

from app import integrity
from app.integrity import IntegrityError


@pytest.fixture
def model_copy(trained, tmp_path):
    import os

    src = Path(os.environ["MODEL_PATH"])
    for f in (src, src.with_suffix(".metrics.json"), integrity.manifest_path(src)):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path / src.name


@pytest.fixture
def use_model(monkeypatch):
    from app import services
    from app.config import settings

    def _use(path):
        monkeypatch.setattr(settings, "model_path", path)
        services._load_forecaster.cache_clear()

    yield _use
    services._load_forecaster.cache_clear()


def test_untouched_model_verifies(model_copy):
    m = integrity.verify(model_copy)
    assert m["data"]["file"] == "sales.csv"


def test_tampered_model_is_detected(model_copy):
    with open(model_copy, "ab") as f:
        f.write(b"\x00")
    with pytest.raises(IntegrityError, match="does not match"):
        integrity.verify(model_copy)


def test_tampered_metrics_are_detected(model_copy):
    metrics = model_copy.with_suffix(".metrics.json")
    metrics.write_text(metrics.read_text().replace('"wape"', '"wape" ', 1))
    with pytest.raises(IntegrityError):
        integrity.verify(model_copy)


def test_missing_manifest_is_refused(model_copy):
    integrity.manifest_path(model_copy).unlink()
    with pytest.raises(IntegrityError, match="no manifest"):
        integrity.verify(model_copy)


def test_api_refuses_tampered_model_and_is_not_ready(client, model_copy, use_model):
    with open(model_copy, "ab") as f:
        f.write(b"tampered")
    use_model(model_copy)

    ready = client.get("/ready")
    assert ready.status_code == 503
    assert "integrity" in ready.json()["status"]

    r = client.get("/forecast/1")
    assert r.status_code == 503
    assert "integrity" in r.json()["detail"]

    assert "model_integrity_ok 0.0" in client.get("/metrics").text


def test_api_recovers_with_a_good_model(client, model_copy, use_model):
    use_model(model_copy)
    assert client.get("/ready").status_code == 200
    assert client.get("/forecast/1").status_code == 200
    assert "model_integrity_ok 1.0" in client.get("/metrics").text
