from prometheus_client import Counter, Gauge

predictions_total = Counter(
    "inventory_predictions_total", "Forecasts served", ["endpoint"]
)
prediction_failures_total = Counter(
    "prediction_failures_total", "Forecasts that failed", ["reason"]
)
recommendations_by_action = Gauge(
    "inventory_recommendations", "Products per recommended action (last computed)", ["action"]
)
expected_waste_units = Gauge(
    "inventory_expected_waste_units", "Units expected to expire unsold in the forecast window"
)
model_mae = Gauge("forecast_model_mae", "MAE of the loaded model on its held-out test set")
model_integrity_ok = Gauge(
    "model_integrity_ok", "1 if the loaded model matches its manifest, 0 if it was refused"
)
