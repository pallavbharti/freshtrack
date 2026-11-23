from datetime import date, datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from tests.conftest import login


@pytest.fixture
def anon(client):
    return TestClient(client.app)


@pytest.fixture
def viewer(client):
    c = TestClient(client.app)
    c.headers["Authorization"] = f"Bearer {login(c, 'viewer')}"
    return c


@pytest.fixture(autouse=True)
def fresh_limiter():
    from app.auth import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.mark.parametrize("path", ["/health", "/ready", "/metrics"])
def test_ops_endpoints_need_no_login(anon, path):
    assert anon.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/products", "/stock", "/sales?product_id=1", "/forecast/1",
                                  "/recommendations", "/model/health", "/auth/me"])
def test_reads_without_token_are_401(anon, path):
    r = anon.get(path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_wrong_password_is_401(anon):
    r = anon.post("/auth/login", json={"username": "manager", "password": "nope"})
    assert r.status_code == 401


def test_unknown_user_gets_the_same_401(anon):
    r = anon.post("/auth/login", json={"username": "nobody", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "wrong username or password"


def test_tampered_token_is_401(anon, viewer):
    token = viewer.headers["Authorization"].split()[1]
    head, body, sig = token.split(".")
    forged = f"{head}.{body}.{sig[:-2]}{'AA' if sig[-2:] != 'AA' else 'BB'}"
    assert anon.get("/products", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_token_signed_with_another_key_is_401(anon):
    fake = jwt.encode({"sub": "manager", "role": "manager",
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, "guessed-secret", algorithm="HS256")
    assert anon.get("/products", headers={"Authorization": f"Bearer {fake}"}).status_code == 401


def test_expired_token_is_401(anon):
    from app.auth import ALGORITHM, _jwt_secret

    old = jwt.encode({"sub": "manager", "role": "manager",
                      "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, _jwt_secret(), algorithm=ALGORITHM)
    assert anon.get("/products", headers={"Authorization": f"Bearer {old}"}).status_code == 401


def test_alg_none_token_is_401(anon):
    unsigned = jwt.encode({"sub": "manager", "role": "manager",
                           "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, None, algorithm="none")
    assert anon.get("/products", headers={"Authorization": f"Bearer {unsigned}"}).status_code == 401


WRITES = [
    ("post", "/products", {"sku": "V-1", "name": "x", "category": "x", "shelf_life_days": 2}),
    ("post", "/stock", {"product_id": 1, "quantity": 1, "received_date": str(date.today()),
                        "expiry_date": str(date.today())}),
    ("post", "/sales", {"product_id": 1, "sale_date": str(date.today()), "quantity": 1}),
    ("post", "/model/backfill", None),
    ("get", "/sales/export", None),
    ("delete", "/stock/1", None),
]


@pytest.mark.parametrize("method,path,body", WRITES)
def test_viewer_cannot_write_403(viewer, method, path, body):
    kwargs = {"json": body} if body else {}
    assert getattr(viewer, method)(path, **kwargs).status_code == 403


@pytest.mark.parametrize("path", ["/products", "/stock", "/recommendations", "/forecast/1", "/model/health"])
def test_viewer_can_read_200(viewer, path):
    assert viewer.get(path).status_code == 200


def test_manager_can_write_200(client):
    r = client.post("/stock", json={"product_id": 1, "quantity": 3, "received_date": str(date.today()),
                                    "expiry_date": str(date.today() + timedelta(days=2))})
    assert r.status_code == 201


def test_me_reports_role(viewer):
    assert viewer.get("/auth/me").json() == {"username": "viewer", "role": "viewer"}


def test_token_is_short_lived(anon):
    r = anon.post("/auth/login", json={"username": "viewer", "password": "viewer-dev-password"})
    body = r.json()
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert body["expires_in"] <= 60 * 60
    assert claims["exp"] - claims["iat"] == body["expires_in"]


def test_login_is_rate_limited(anon):
    for _ in range(5):
        assert anon.post("/auth/login", json={"username": "manager", "password": "guess"}).status_code == 401
    r = anon.post("/auth/login", json={"username": "manager", "password": "guess"})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    r = anon.post("/auth/login", json={"username": "manager", "password": "manager-dev-password"})
    assert r.status_code == 429


def test_spoofed_forwarded_for_does_not_reset_the_limit(anon):
    for i in range(5):
        anon.post("/auth/login", json={"username": "viewer", "password": "guess"},
                  headers={"X-Forwarded-For": f"1.2.3.{i}, 10.0.0.7"})
    r = anon.post("/auth/login", json={"username": "viewer", "password": "guess"},
                  headers={"X-Forwarded-For": "9.9.9.9, 10.0.0.7"})
    assert r.status_code == 429


def test_password_is_hashed_with_argon2(client):
    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        h = db.query(User).filter(User.username == "manager").one().password_hash
    assert h.startswith("$argon2id$")
    assert "manager-dev-password" not in h
