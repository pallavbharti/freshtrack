import json
from pathlib import Path

NS = 'namespace=~"$namespace"'


def panel(pid, title, exprs, x, y, w=12, h=8, kind="timeseries", unit=None, legend=None):
    targets = []
    for i, e in enumerate(exprs if isinstance(exprs, list) else [exprs]):
        t = {"expr": e, "refId": chr(65 + i)}
        if legend:
            t["legendFormat"] = legend[i] if isinstance(legend, list) else legend
        targets.append(t)
    p = {
        "id": pid,
        "title": title,
        "type": kind,
        "datasource": {"type": "prometheus", "uid": "${datasource}"},
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": targets,
        "fieldConfig": {"defaults": {}, "overrides": []},
    }
    if unit:
        p["fieldConfig"]["defaults"]["unit"] = unit
    return p


panels = [
    panel(1, "Healthy backend pods", f'sum(up{{job="backend",{NS}}})', 0, 0, w=6, h=5, kind="stat"),
    panel(2, "Requests / sec", f'sum(rate(http_requests_total{{job="backend",{NS}}}[5m]))',
          6, 0, w=6, h=5, kind="stat", unit="reqps"),
    panel(3, "Error rate (5xx)",
          f'sum(rate(http_requests_total{{job="backend",status="5xx",{NS}}}[5m])) '
          f'/ clamp_min(sum(rate(http_requests_total{{job="backend",{NS}}}[5m])), 1e-9)',
          12, 0, w=6, h=5, kind="stat", unit="percentunit"),
    panel(4, "Model MAE (held-out)", f'max(forecast_model_mae{{{NS}}})', 18, 0, w=6, h=5, kind="stat"),

    panel(5, "Request rate by endpoint",
          f'sum by (handler) (rate(http_requests_total{{job="backend",{NS}}}[5m]))',
          0, 5, unit="reqps", legend="{{handler}}"),
    panel(6, "Latency p50 / p95",
          [f'histogram_quantile(0.5, sum by (le) (rate(http_request_duration_seconds_bucket{{job="backend",{NS}}}[5m])))',
           f'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{job="backend",{NS}}}[5m])))'],
          12, 5, unit="s", legend=["p50", "p95"]),

    panel(7, "Responses by status",
          f'sum by (status) (rate(http_requests_total{{job="backend",{NS}}}[5m]))',
          0, 13, unit="reqps", legend="{{status}}"),
    panel(8, "Pod restarts (last 1h)",
          f'sum by (pod) (increase(kube_pod_container_status_restarts_total{{{NS}}}[1h]))',
          12, 13, legend="{{pod}}"),

    panel(9, "Prediction failures",
          f'sum by (reason) (increase(prediction_failures_total{{{NS}}}[5m]))',
          0, 21, legend="{{reason}}"),
    panel(10, "Recommendations by action",
          f'max by (action) (inventory_recommendations{{{NS}}})', 12, 21, legend="{{action}}"),
    panel(11, "Units expected to expire (next 7 days)",
          f'max(inventory_expected_waste_units{{{NS}}})', 0, 29, w=24, h=7, legend="expected waste"),

    panel(12, "Live forecast WAPE, 7 days (%)",
          f'max by (sku) (forecast_wape_7d{{{NS}}})', 0, 36, unit="percent", legend="{{sku}}"),
    panel(13, "Store: live WAPE / held-out WAPE (ModelDegraded above 1.45)",
          f'max(forecast_wape_7d_store{{{NS}}}) / max(forecast_holdout_wape_store{{{NS}}})',
          12, 36, legend="ratio"),
    panel(14, "Store forecast bias, 7 days (%) - above 0 = over-forecast",
          f'max(forecast_bias_7d_store{{{NS}}})', 0, 44, unit="percent", legend="bias"),
    panel(15, "Data drift: median PSI across products (alert above 0.25)",
          f'max(data_drift_psi_store{{{NS}}})', 12, 44, legend="store median PSI"),
    panel(16, "Data drift PSI per product",
          f'max by (sku) (data_drift_psi{{{NS}}})', 0, 52, w=24, h=7, legend="{{sku}}"),
]

dashboard = {
    "uid": "freshtrack",
    "title": "FreshTrack - API, pipeline and inventory health",
    "timezone": "browser",
    "schemaVersion": 39,
    "refresh": "30s",
    "time": {"from": "now-6h", "to": "now"},
    "templating": {
        "list": [
            {"name": "datasource", "type": "datasource", "query": "prometheus", "label": "Data source"},
            {
                "name": "namespace",
                "type": "custom",
                "label": "Environment",
                "query": "freshtrack-prod,freshtrack-staging",
                "current": {"text": "freshtrack-prod", "value": "freshtrack-prod"},
            },
        ]
    },
    "panels": panels,
}

body = json.dumps(dashboard, indent=2)
indented = "\n".join("    " + line for line in body.splitlines())

configmap = f"""\
apiVersion: v1
kind: ConfigMap
metadata:
  name: freshtrack-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  freshtrack.json: |
{indented}
"""

out = Path(__file__).with_name("grafana-dashboard.yaml")
out.write_text(configmap)
print(f"wrote {out}")
