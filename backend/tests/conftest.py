import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmp = Path(tempfile.mkdtemp(prefix="freshtrack-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["MODEL_PATH"] = str(_tmp / "model.joblib")
os.environ["SEED_DATA_PATH"] = str(_tmp / "sales.csv")
os.environ["SEED_ON_START"] = "true"

from app.ml.forecaster import save, train  # noqa: E402
from scripts.generate_sales import generate  # noqa: E402


@pytest.fixture(scope="session")
def sales_df():
    df = generate(days=400, seed=123, end=date(2026, 6, 30))
    df.to_csv(os.environ["SEED_DATA_PATH"], index=False)
    return df


@pytest.fixture(scope="session")
def trained(sales_df):
    model, metrics = train(sales_df)
    save(model, metrics, Path(os.environ["MODEL_PATH"]), data_path=Path(os.environ["SEED_DATA_PATH"]))
    return model, metrics


@pytest.fixture(scope="session")
def client(trained):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {login(c, 'manager')}"
        yield c


def login(client, role: str) -> str:
    r = client.post("/auth/login", json={"username": role, "password": f"{role}-dev-password"},
                    headers={"Authorization": ""})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]
