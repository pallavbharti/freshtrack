import json
import os
import sys
from pathlib import Path

MAX_WAPE = float(os.getenv("MODEL_MAX_WAPE", "20"))
MODELS_DIR = (Path(__file__).resolve().parents[1] / "models").resolve()


def check(metrics: dict) -> list[str]:
    problems = []
    model, naive = metrics["model"]["wape"], metrics["naive_lag7"]["wape"]
    if model > MAX_WAPE:
        problems.append(f"WAPE {model}% is above the limit {MAX_WAPE}%")
    if model >= naive:
        problems.append(f"WAPE {model}% does not beat the naive lag-7 forecast ({naive}%)")
    return problems


def metrics_path(arg: str | None) -> Path:
    path = Path(arg or "forecast_model.metrics.json")
    if not path.is_absolute():
        path = MODELS_DIR / path.name if path.parent == Path("models") else MODELS_DIR / path
    path = path.resolve()
    if not path.is_relative_to(MODELS_DIR) or path.suffix != ".json":
        raise SystemExit(f"refusing to read {path}: only .json files inside {MODELS_DIR} are allowed")
    return path


def main():
    path = metrics_path(sys.argv[1] if len(sys.argv) > 1 else None)
    metrics = json.loads(path.read_text())
    problems = check(metrics)
    print(f"model WAPE {metrics['model']['wape']}% | naive {metrics['naive_lag7']['wape']}% | limit {MAX_WAPE}%")
    for p in problems:
        print(f"FAIL: {p}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
