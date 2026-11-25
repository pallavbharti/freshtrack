# FreshTrack

### Smarter inventory decisions. Safer deployments. Less food waste.

FreshTrack is an intelligent inventory management system built for perishable food products. It predicts upcoming demand, tracks stock and expiry dates, and helps answer two practical questions for a store:

**What should we reorder?**  

Building the forecasting model is only one part of the problem. A model update can improve prediction accuracy and still lead to poor inventory decisions, such as higher food waste or more stockouts.

**What is likely to expire before we can sell it?**

FreshTrack addresses this by combining inventory intelligence with a secure CI/CD and monitoring workflow. Every important change is tested, evaluated against business KPIs, scanned for security issues, and monitored after deployment.

## What makes FreshTrack different?

Many ML projects end once the model produces a prediction. FreshTrack focuses on what happens after that prediction is used in a real inventory workflow.

Before a change can move toward deployment, FreshTrack checks:

- **Code and API tests:** Verify that the application behaves as expected.
- **Model quality:** Ensure forecasting performance remains within acceptable limits.
- **Business KPIs:** Block changes that increase expected food waste, increase stockouts, or reduce fill rate.
- **Security:** Scan source code, dependencies, containers, secrets, and infrastructure.
- **Model integrity:** Verify model and data artifacts using SHA-256 manifests.
- **Live performance:** Monitor forecast error, bias, data drift, and application health after deployment.
- **Retraining:** Pass updated models through the same validation process before they can replace the deployed model.

FreshTrack therefore goes beyond building a forecasting model and dashboard. The project covers the broader lifecycle of an ML-powered inventory system, from historical sales data and demand forecasting to inventory decisions, deployment, monitoring, and retraining.

## System at a glance

### Inventory Intelligence

`Sales History → Demand Forecast → Expiry Simulation → Reorder or Expiry Risk Recommendation`

### Delivery Pipeline

`Git Push → Tests → Model and Business Gates → Security Scans → Docker → Kubernetes → Monitoring`

### Feedback Loop

`Live Sales → Forecast Error and Drift → Alert → Retraining → Validation → Pull Request → Deployment`

## Tech Stack

| Area | Technologies |
|---|---|
| Frontend | React 19, Vite, nginx |
| Backend | FastAPI, SQLAlchemy |
| Database | PostgreSQL, SQLite |
| Machine Learning | scikit-learn, GradientBoostingRegressor |
| CI/CD | GitHub Actions |
| Containers | Docker |
| Deployment | Kubernetes |
| Security | SonarQube Cloud, Trivy, Gitleaks, Cosign |
| Monitoring | Prometheus, Grafana |
| Testing | Pytest, Vitest |
