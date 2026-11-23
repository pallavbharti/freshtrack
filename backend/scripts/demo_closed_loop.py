import argparse
import json
import os
import urllib.request
from datetime import date, timedelta


class Api:
    def __init__(self, base: str, token: str | None):
        self.base = base.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else None


def status(api: Api):
    h = api.call("GET", "/model/health")
    st = h["store"]
    ratio = st["wape_7d"] / st["holdout_wape"] if st["wape_7d"] and st["holdout_wape"] else None
    print(f"store: live WAPE {st['wape_7d']}% vs held-out (as served) {st['holdout_wape']}%"
          f" -> ratio {ratio:.2f}" if ratio else f"store: {st}")
    print(f"       bias {st['bias_7d']}%   evaluated days {st['eval_days']}")
    print(f"       median PSI {h['store_psi']}  (DataDrift alert above 0.25)")
    if ratio:
        print(f"       ModelDegraded alert above ratio 1.45: {'WOULD FIRE' if ratio > 1.45 else 'ok'}")
    print("\nper product:")
    for sku, e in h["products"].items():
        print(f"  {sku:8} WAPE {e['wape_7d']!s:>6}  bias {e['bias_7d']!s:>7}  PSI {e['psi']!s:>7}")


def backfill(api: Api, days: int):
    r = api.call("POST", f"/model/backfill?days={days}")
    print(f"backfilled {sum(r['forecasts_added'].values())} forecasts over {days} days")


def shift(api: Api, factor: float, days: int):
    today = date.today()
    for p in api.call("GET", "/products"):
        sales = api.call("GET", f"/sales?product_id={p['id']}&days={days}")
        extra = {s["sale_date"]: round(s["quantity"] * (factor - 1)) for s in sales
                 if s["sale_date"] < today.isoformat()}
        extra = {d: q for d, q in extra.items() if q > 0}
        if not extra:
            continue
        api.call("POST", "/stock", {
            "product_id": p["id"], "quantity": sum(extra.values()),
            "received_date": (today - timedelta(days=days + 1)).isoformat(),
            "expiry_date": today.isoformat(),
        })
        for d, q in sorted(extra.items()):
            api.call("POST", "/sales", {"product_id": p["id"], "sale_date": d, "quantity": q})
        print(f"{p['sku']}: +{sum(extra.values())} units over {len(extra)} days")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("API_URL", "http://localhost:8000"))
    parser.add_argument("--token", default=os.getenv("API_TOKEN"))
    parser.add_argument("--username", default="manager")
    parser.add_argument("--password", default=os.getenv("MANAGER_PASSWORD", "manager-dev-password"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    b = sub.add_parser("backfill")
    b.add_argument("--days", type=int, default=14)
    s = sub.add_parser("shift")
    s.add_argument("--factor", type=float, default=1.4)
    s.add_argument("--days", type=int, default=28)
    args = parser.parse_args()

    api = Api(args.base_url, args.token)
    if not api.token:
        creds = {"username": args.username, "password": args.password}
        api.token = api.call("POST", "/auth/login", creds)["access_token"]
    if args.cmd == "status":
        status(api)
    elif args.cmd == "backfill":
        backfill(api, args.days)
    else:
        shift(api, args.factor, args.days)


if __name__ == "__main__":
    main()
