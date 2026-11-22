import numpy as np

BINS = 4
REFERENCE_DAYS = 90
RECENT_DAYS = 28
SMOOTHING = 0.5


def build_reference(values, bins: int = BINS) -> dict:
    values = np.asarray(values, dtype=float)
    edges = np.unique(np.quantile(values, np.linspace(0, 1, bins + 1)[1:-1]))
    return {"edges": [float(e) for e in edges], "probs": _proportions(values, edges)}


def _proportions(values, edges) -> list[float]:
    k = len(edges) + 1
    counts = np.bincount(np.searchsorted(edges, np.asarray(values, dtype=float), side="right"), minlength=k)
    return [float(p) for p in (counts + SMOOTHING) / (len(values) + SMOOTHING * k)]


def psi(reference: dict, recent_values) -> float:
    if len(recent_values) == 0:
        return 0.0
    expected = np.asarray(reference["probs"])
    actual = np.asarray(_proportions(recent_values, np.asarray(reference["edges"])))
    return float(np.sum((actual - expected) * np.log(actual / expected)))
