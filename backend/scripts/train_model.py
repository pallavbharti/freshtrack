import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml.forecaster import save, train  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/sales.csv")
    parser.add_argument("--out", default="models/forecast_model.joblib")
    args = parser.parse_args()

    sales = pd.read_csv(args.data)
    model, metrics = train(sales)
    save(model, metrics, Path(args.out), data_path=Path(args.data))

    print(json.dumps(metrics, indent=2))
    print(f"model saved to {args.out}")


if __name__ == "__main__":
    main()
