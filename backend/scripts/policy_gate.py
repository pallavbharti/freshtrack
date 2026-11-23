import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_CONFIG = ROOT / "policy_gate.yaml"
DEFAULT_BASELINE = ROOT.parent / "results" / "baseline_kpis.json"


@dataclass
class Check:
    name: str
    value: float
    limit: float
    passed: bool
    detail: str


def _check(name, value, limit, ok, detail) -> Check:
    return Check(name, round(float(value), 3), round(float(limit), 3), bool(ok), detail)


def evaluate(candidate: dict, reference: dict | None, config: dict) -> list[Check]:
    checks = []
    ours = candidate["policies"]["ours"]

    if reference is not None:
        ref = reference["policies"]["ours"]
        r = config["regression"]
        d = ours["waste_rate"] - ref["waste_rate"]
        checks.append(_check("waste_rate vs main", d, r["max_waste_rate_increase_pp"],
                             d <= r["max_waste_rate_increase_pp"],
                             f"{ref['waste_rate']:.3f}% -> {ours['waste_rate']:.3f}%"))
        d = ref["fill_rate"] - ours["fill_rate"]
        checks.append(_check("fill_rate vs main", d, r["max_fill_rate_drop_pp"],
                             d <= r["max_fill_rate_drop_pp"],
                             f"{ref['fill_rate']:.3f}% -> {ours['fill_rate']:.3f}%"))
        d = ours["stockout_days"] - ref["stockout_days"]
        checks.append(_check("stockout_days vs main", d, r["max_stockout_days_increase"],
                             d <= r["max_stockout_days_increase"],
                             f"{ref['stockout_days']} -> {ours['stockout_days']}"))
        d = candidate["forecast_wape"] - reference["forecast_wape"]
        checks.append(_check("forecast WAPE vs main", d, r["max_forecast_wape_increase_pp"],
                             d <= r["max_forecast_wape_increase_pp"],
                             f"{reference['forecast_wape']:.2f}% -> {candidate['forecast_wape']:.2f}%"))

    c = config["policy_comparison"]
    base = candidate["policies"]["baseline"]
    d = ours["waste_rate"] - base["waste_rate"]
    lim = c["vs_baseline"]["max_waste_rate_excess_pp"]
    checks.append(_check("ours vs baseline policy: waste", d, lim, d <= lim,
                         f"ours {ours['waste_rate']:.3f}% vs baseline {base['waste_rate']:.3f}%"))
    d = base["fill_rate"] - ours["fill_rate"]
    lim = c["vs_baseline"]["max_fill_rate_shortfall_pp"]
    checks.append(_check("ours vs baseline policy: fill", d, lim, d <= lim,
                         f"ours {ours['fill_rate']:.3f}% vs baseline {base['fill_rate']:.3f}%"))
    rep = candidate["policies"]["replenish"]
    d = ours["fill_rate"] - rep["fill_rate"]
    lim = c["vs_replenish"]["min_fill_rate_gain_pp"]
    checks.append(_check("ours vs replenish policy: fill gain", d, lim, d >= lim,
                         f"ours {ours['fill_rate']:.3f}% vs replenish {rep['fill_rate']:.3f}%"))

    a = config["absolute"]
    checks.append(_check("waste_rate absolute", ours["waste_rate"], a["max_waste_rate"],
                         ours["waste_rate"] <= a["max_waste_rate"], "max allowed"))
    checks.append(_check("fill_rate absolute", ours["fill_rate"], a["min_fill_rate"],
                         ours["fill_rate"] >= a["min_fill_rate"], "min allowed"))
    checks.append(_check("forecast WAPE absolute", candidate["forecast_wape"], a["max_forecast_wape"],
                         candidate["forecast_wape"] <= a["max_forecast_wape"], "max allowed"))
    return checks


def markdown(candidate: dict, reference: dict | None, checks: list[Check]) -> str:
    passed = all(c.passed for c in checks)
    lines = [
        f"## Business-KPI gate: {'PASSED' if passed else 'FAILED'}",
        "",
        "_Simulated on synthetic data (60 held-out days). Not results from a real store._",
        "",
        "| Policy | Waste rate % | Fill rate % | Stockout days | Lost sales |",
        "|---|---|---|---|---|",
    ]
    for name, k in candidate["policies"].items():
        lines.append(f"| {name} | {k['waste_rate']:.3f} | {k['fill_rate']:.3f} "
                     f"| {k['stockout_days']} | {k['lost_sales']} |")
    if reference:
        k = reference["policies"]["ours"]
        lines.append(f"| ours on main (reference) | {k['waste_rate']:.3f} | {k['fill_rate']:.3f} "
                     f"| {k['stockout_days']} | {k['lost_sales']} |")
    lines += ["", f"Forecast WAPE: **{candidate['forecast_wape']:.2f}%**", "",
              "| Check | Result | Value | Limit | Detail |", "|---|---|---|---|---|"]
    for c in checks:
        lines.append(f"| {c.name} | {'✅ pass' if c.passed else '❌ FAIL'} | {c.value} | {c.limit} | {c.detail} |")
    if reference and reference["data"]["sha256"] != candidate["data"]["sha256"]:
        lines += ["", "⚠️ The dataset differs from the one the reference was computed on, "
                  "so the comparison with main is less strict than usual."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="reference KPI JSON (from main)")
    parser.add_argument("--data", help="sales CSV; default is the fixed synthetic dataset")
    parser.add_argument("--candidate", help="use an existing KPI JSON instead of running the simulation")
    parser.add_argument("--out", help="write candidate KPIs + gate result to this JSON file")
    parser.add_argument("--summary", help="append a markdown report here (e.g. $GITHUB_STEP_SUMMARY)")
    parser.add_argument("--write-baseline", action="store_true",
                        help="save the candidate KPIs as the new reference (only if the gate passes)")
    parser.add_argument("--accept-regression", metavar="REASON",
                        help="with --write-baseline: save even though the gate fails, recording why")
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text())

    if args.candidate:
        candidate = json.loads(Path(args.candidate).read_text())
    else:
        from scripts.simulate import build_report, load_or_generate

        sales, source = load_or_generate(args.data)
        _, candidate = build_report(sales, source)

    baseline_path = Path(args.baseline)
    reference = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
    if reference is None:
        print(f"note: no reference at {baseline_path}, only the comparison and absolute checks run")

    checks = evaluate(candidate, reference, config)
    passed = all(c.passed for c in checks)
    report = markdown(candidate, reference, checks)
    print(report)

    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write(report)
    if args.out:
        result = dict(candidate, gate={"passed": passed, "checks": [asdict(c) for c in checks]})
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")

    if args.write_baseline:
        if not passed and not args.accept_regression:
            print("refusing to write the baseline: the gate failed. "
                  "Use --accept-regression \"reason\" if this is a deliberate, reviewed change.")
            sys.exit(1)
        new_ref = dict(candidate)
        new_ref["accepted"] = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "gate_passed": passed,
            "reason": args.accept_regression or "gate passed",
        }
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(new_ref, indent=2) + "\n")
        print(f"reference KPIs written to {baseline_path}")
        return

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
