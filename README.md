#FreshTrack: Secure CI/CD for an Intelligent Food-Retail Inventory System

FreshTrack has two parts:

1. **An inventory app** that forecasts demand for perishable products, tracks stock batch by batch with expiry dates, and recommends what to reorder and what is likely to expire unsold.
2. **A secure CI/CD pipeline** that tests, scans, packages, deploys and monitors the app on every change to the code or the model.

Our contribution is not a new forecasting algorithm or a new pipeline tool. We put the two together into one secure, continuously monitored delivery framework for food-retail inventory.

> **What is new here** (details and evidence in [`docs/novelty.md`](docs/novelty.md)): a **business-KPI deployment gate** (does this change make the store waste more food or run out more often?), a **closed loop** after deployment (live forecast error and drift → alert → retrain through the same gates), **ML supply-chain checks** (data validation, model integrity manifest, signed images with SBOM), and **fault-injection evidence** against a generic pipeline. Dataset: [`docs/dataset.md`](docs/dataset.md). Demo: [`docs/demo.md`](docs/demo.md). Report text: [`docs/report-snippets.md`](docs/report-snippets.md).

## Architecture

```
 Developer ── git push / PR ──► GitHub Actions (all actions pinned to commit SHAs)
                            │
                            ├─ 1. lint + unit/API tests + training-data validation vs main   (ruff, pytest, validate_data.py)
                            ├─ 2. BUSINESS-KPI GATE: simulated waste / fill / stockouts vs main (policy_gate.py)
                            │     alert-rule unit tests                                       (promtool)
                            │     frontend tests + build + npm audit                          (Vitest)
                            ├─ 3. SonarQube Cloud (required on main) · Gitleaks (history) · Trivy fs (vuln, secret, misconfig)
                            ├─ 4. docker build (trains + checks model, writes SHA-256 manifest)
                            │     ─► container smoke test (model integrity) ─► Trivy image scan ─► SBOM
                            │     ─► push to GHCR ─► cosign keyless sign + SBOM attestation   (main only)
                            ├─ 5. deploy to staging: verify signature ─► deploy by digest ─► smoke test ─► rollback on failure
                            └─ 6. deploy to production (optional manual approval)
                                          │
                     Kubernetes ◄─────────┘
                     ├─ frontend (React + nginx with CSP, 2 replicas)
                     ├─ backend  (FastAPI + scikit-learn, JWT roles, 2 replicas, /health /ready probes)
                     └─ postgres (StatefulSet)
                                          │ /metrics (inside the cluster only)
                     Prometheus ◄─────────┘ ─► Grafana + alerts (incl. ModelDegraded, DataDrift, ModelIntegrityFailed)
                                          │
                                          └─► retrain.yml: export ─► validate data ─► train ─► model + business gates ─► PR
```

| Layer | Tool |
|---|---|
| Frontend | React 19 (Vite), served by nginx |
| Backend | FastAPI, SQLAlchemy |
| Database | PostgreSQL (SQLite for tests / quick local runs) |
| Forecasting | scikit-learn GradientBoostingRegressor |
| CI | GitHub Actions |
| Code security | SonarQube Cloud, Trivy (filesystem: dependencies, secrets, Dockerfile/K8s misconfig) |
| Container security | Trivy image scan, non-root images, read-only root filesystem |
| Packaging | Docker (multi-stage builds) |
| Deployment | Kubernetes (minikube / kind / k3s) |
| Monitoring | Prometheus + Grafana (kube-prometheus-stack) |

## Repository layout

```
backend/
  app/
    main.py            FastAPI app, /health, /ready, /metrics
    auth.py            Argon2 passwords, JWT, roles, login rate limit
    inventory.py       reorder + expiry-risk logic, plan_order (pure functions)
    monitoring.py      forecast log scoring: live WAPE, bias, drift -> Prometheus
    integrity.py       model manifest (SHA-256) written at training, verified at startup
    services.py        glue between the database, the model and inventory.py
    ml/features.py     feature engineering (shared by training and serving)
    ml/forecaster.py   training, evaluation, recursive multi-day forecast
    ml/drift.py        PSI drift score
    routers/           /auth /products /stock /sales /forecast /recommendations /model/*
    seed.py            demo data loader
  scripts/
    generate_sales.py  synthetic sales dataset
    train_model.py     trains the model, saves metrics
    simulate.py        deterministic offline evaluation: three policies, JSON KPIs
    policy_gate.py     business-KPI gate (vs results/baseline_kpis.json)
    validate_data.py   training-data validation and profile
    check_model.py     quality check of a trained model file
    demo_closed_loop.py  backfill / status / shift demo for the closed loop
  data/                versioned dataset snapshot + its profile
  tests/               unit, API and model-quality tests
frontend/              React dashboard (login, roles) + nginx config (CSP), Vitest tests
docs/                  novelty statement, demo script, report snippets
faults/                fault catalogue for the injection experiment
results/               reference KPIs and real experiment outputs only
k8s/                   Deployments, Services, StatefulSet, NetworkPolicy
monitoring/            Helm values, ServiceMonitor, alert rules, Grafana dashboard
scripts/               deploy (signature check), smoke test, export, retrain trigger,
                       fault injection + experiment runner, action pinning
.github/workflows/     ci-cd.yml (full), ci-basic.yml (comparison), retrain.yml,
                       update-baseline.yml
```

## How the inventory logic works

For each product, every time recommendations are requested:

1. **Forecast** daily demand for the next 7 days. One global model for all products. Features: lags of 1, 7 and 14 days, 7- and 28-day rolling means, 7-day rolling std, day of week, weekend, promotion and holiday flags.
2. **Simulate the next 7 days on the shelf.** Sell the oldest-expiry batch first (FEFO). Any units still on the shelf after their expiry date are counted as *expected waste*. `usable_stock = on_hand - expected_waste`.
3. **Decide:**
   - `REORDER` if usable stock < demand until the next delivery + safety stock. Demand is covered for lead time + 1 day, because orders are reviewed daily. Safety stock = z × σ(daily demand) × √(cover days), with z = 1.65 (about a 95% service level).
   - `EXPIRY_RISK` if some units are expected to expire unsold (mark them down or donate them).
   - `OK` otherwise.

`REORDER` takes priority over `EXPIRY_RISK`, because running out is usually the bigger loss for the store. The expected waste is still reported for that product.

## Running it locally

### Option A: plain Python + Node (fastest for development)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python scripts/generate_sales.py
python scripts/train_model.py
uvicorn app.main:app --reload                          # http://localhost:8000/docs

# second terminal
cd frontend
npm install
npm run dev                                            # http://localhost:5173
```

This uses SQLite (`backend/inventory.db`). Delete that file to reset the demo data.

Log in with **manager / manager-dev-password** (can change data) or **viewer / viewer-dev-password** (read-only). These dev accounts exist only when `APP_ENV` is not `production`. In production, the passwords come from secrets, and the API refuses to start without them.

### Option B: Docker Compose (Postgres, same images as production)

```bash
cp .env.example .env          # then set every value inside .env
docker compose up --build
```

Dashboard: http://localhost:3000 (log in with `manager` or `viewer` and the passwords from `.env`). API docs: http://localhost:8000/docs (only on the direct backend port; nginx blocks `/docs` and `/metrics`).

### Tests

```bash
cd backend
pytest --cov=app
ruff check .
```

`tests/test_model.py` is the **model quality gate**. It fails the build if the forecast WAPE or MAE goes above the limit, or if the model stops beating a naive "same day last week" forecast. The limits can be changed with `MODEL_MAX_WAPE` / `MODEL_MAX_MAE`.

**Why WAPE?** WAPE = sum(|actual − forecast|) / sum(actual). Daily sales of a slow item can be 0, which makes MAPE divide by zero (or explode). WAPE stays defined and weights errors by volume. MAE, RMSE and MAPE are still reported for reference, but every gate uses WAPE.

## Setting up the pipeline

### 1. Push the repo to GitHub

The workflow runs on every push and pull request to `main`. Lint, tests, the build and the Trivy scans need no setup.

### 2. SonarQube Cloud (free for public repos)

A GitHub-hosted runner cannot reach a SonarQube server running on your laptop, so we use SonarQube Cloud.

1. Sign in at https://sonarcloud.io with GitHub and import the repository.
2. In the project, turn off *Automatic Analysis* (Administration → Analysis Method). We run the analysis from CI so that coverage is included.
3. Create a token (My Account → Security) and add it to the repo as the secret `SONAR_TOKEN`.
4. Add two repository **variables** (Settings → Secrets and variables → Actions → Variables): `SONAR_ORGANIZATION` (your SonarCloud organization key) and `SONAR_PROJECT_KEY` (shown on the project page, usually `<org>_freshtrack`).

On `main`, a missing token or variable **fails** the pipeline: code never reaches production without the quality gate. On other branches and PRs, the Sonar step is skipped with a warning (secrets are not available to PRs from forks).

### 3. Container registry

Images are pushed to GitHub Container Registry as `ghcr.io/<owner>/freshtrack-backend` and `-frontend`. After the first successful push, open each package on GitHub (your profile → Packages → Package settings) and set its visibility to **Public**, so the cluster can pull the images without credentials.

### 4. Kubernetes cluster + self-hosted runner

A GitHub-hosted runner cannot reach a minikube cluster on your laptop. The simplest setup for the demo is a **self-hosted runner on the same machine as minikube**:

1. Install Docker, kubectl and minikube, then run `minikube start --cpus 4 --memory 6g`.
2. Repo → Settings → Actions → Runners → *New self-hosted runner*. Choose **Linux** and follow the commands. On Windows, install the runner inside WSL2 (Ubuntu), because the deploy scripts are bash. The runner needs the labels `self-hosted` and `linux` (added by default).
3. Make sure `kubectl get nodes` and `python3 --version` work in the shell the runner uses (`deploy.sh` uses python3 to read cosign's output; cosign itself is installed by the workflow). The pinned actions run on Node 24, so keep the runner up to date (it auto-updates by default).
4. Repo → Settings → Environments: create `staging` and `production`. In **each** environment, add three secrets with the same names but different values:
   - `DB_PASSWORD`: Postgres password
   - `MANAGER_PASSWORD`, `VIEWER_PASSWORD`: the two app logins

   `deploy.sh` turns them into Kubernetes Secrets. It also generates the JWT signing key inside the cluster once per namespace, and it never leaves the cluster. (Optional) under `production`, add yourself as a *required reviewer* to get a manual approval step. The retrain export job uses the `production` environment too, so it also waits for that approval.

Alternatives: run k3s on a free-tier cloud VM and install the runner there.

### 5. Monitoring

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace \
  -f monitoring/kube-prometheus-values.yaml \
  --set grafana.adminPassword='choose-one'

kubectl apply -f monitoring/servicemonitor.yaml -f monitoring/alert-rules.yaml -f monitoring/grafana-dashboard.yaml

kubectl -n monitoring port-forward svc/monitoring-grafana 3001:80   # http://localhost:3001 (admin / your password)
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090
```

The service names above depend on the Helm release name (`monitoring`). Check them with `kubectl -n monitoring get svc`.

Alerts: BackendDown, BackendReplicaMissing, PodRestartingOften, HighErrorRate, SlowResponses, PredictionFailures, HighExpectedWaste (a business alert).

### Manual deploy (without the pipeline)

```bash
export OWNER=<your-github-username> REPO=<owner>/<repo>
export DB_PASSWORD=<password> MANAGER_PASSWORD=<password> VIEWER_PASSWORD=<password>
./scripts/deploy.sh freshtrack-staging latest
./scripts/smoke-test.sh freshtrack-staging          # uses VIEWER_PASSWORD
minikube service frontend -n freshtrack-staging     # opens the dashboard
kubectl -n freshtrack-staging rollout undo deployment/backend   # rollback
```

## Business-KPI deployment gate

Unit tests check that the code does what the code says. They cannot tell whether a change makes the store **waste more food or run out of stock more often**. The `business-gate` CI job checks exactly that, before any image is built or deployed.

1. `backend/scripts/policy_gate.py` runs the deterministic simulation on the candidate code and model (60 held-out days, three ordering policies).
2. It compares the KPIs with `results/baseline_kpis.json`, the reference KPIs of what is on `main`.
3. It fails if any limit in `backend/policy_gate.yaml` is broken:
   - waste rate rises, fill rate falls, stockout days rise, or forecast WAPE rises beyond tolerance (vs `main`)
   - our policy becomes worse than the moving-average baseline policy beyond tolerance, or stops clearly beating the "re-order what sold" habit (same run)
   - absolute limits on waste rate, fill rate and WAPE
4. A KPI table is written to the job summary, and the JSON is uploaded as the `business-kpis` artifact.

The image build and both deploy jobs `need` this job, so a change that fails it is never built or deployed.

Run it locally:

```bash
cd backend
python scripts/policy_gate.py              # exit code 0 = pass, 1 = fail
```

**Changing the reference (deliberately).** The reference never changes automatically. After a reviewed change that moves the KPIs, run the *Update business-KPI baseline* workflow from the Actions tab and give a reason. It recomputes the KPIs and opens a PR that updates `results/baseline_kpis.json`. It refuses if the gate fails, unless *accept_regression* is ticked; the reason is then recorded in the JSON. Locally:

```bash
python scripts/policy_gate.py --write-baseline
python scripts/policy_gate.py --write-baseline --accept-regression "reason"
```

For the workflow to open PRs, enable *Settings → Actions → General → Allow GitHub Actions to create and approve pull requests*.

## Closed-loop monitoring and retraining

Generic monitoring checks if the service is *up*. FreshTrack also checks whether the deployed model is still *right*, using real sales as they arrive.

1. **Every forecast the API serves is logged** (`forecast_log` table): the first forecast per product, day and horizon.
2. **When sales are recorded** (`POST /sales`), the actual quantity is written next to the forecast for that day.
3. **Prometheus metrics** are computed from the log at scrape time (same numbers on every replica):

| Metric | Meaning |
|---|---|
| `forecast_wape_7d{sku}`, `forecast_wape_7d_store` | live WAPE over the last 7 **closed** days |
| `forecast_holdout_wape{sku}`, `forecast_holdout_wape_store` | WAPE on held-out data at training, scored "as served" (promo/holiday unknown, like the live API) |
| `forecast_bias_7d{sku}`, `forecast_bias_7d_store` | (forecast − actual) / actual; > 0 means over-forecasting, a waste risk |
| `data_drift_psi{sku}`, `data_drift_psi_store` | PSI of the last 28 days of sales vs the last 90 training days; store value = median across products |

4. **Alerts** (`monitoring/alert-rules.yaml`, unit-tested with promtool in CI):
   - `ModelDegraded`: store live WAPE > 1.45 × held-out WAPE, with at least 3 evaluated days
   - `DataDrift`: median PSI > 0.25 for 30 minutes
   - `ForecastBiased`: |store bias| > 15% for 1 hour
5. **Retrain** (`.github/workflows/retrain.yml`): manual, weekly, or `repository_dispatch`. It exports the latest sales from production (self-hosted runner) or uses the committed snapshot. Then it runs **data validation → model quality check → business-KPI gate**. Only if all three pass does it open a PR that updates `backend/data/sales.csv`. Merging that PR runs the normal pipeline, which trains the deployed model from that snapshot inside the Docker build.

**Why these thresholds.** They were measured on our synthetic data, not guessed. They will need recalibrating on real data.
- A single product's 7-day WAPE swung up to about 2× its held-out value in normal weeks, so alerts use store-level numbers.
- Across 3 datasets, the normal store ratio peaked at 1.42. A degraded model (no lag features) or a +40% demand shift reached at least 1.49. That margin is narrow.
- Store median PSI stayed ≤ 0.134 in normal windows and was ≥ 0.325 after a ±25% demand shift.
- A +25% shift does *not* trip `ModelDegraded` (the model adapts through its lag features), but `DataDrift` catches it.

**Demo** (local API or a port-forward to staging):

```bash
cd backend
python scripts/demo_closed_loop.py backfill          # model's backtest forecasts for the last 14 days
python scripts/demo_closed_loop.py status            # ratio ~0.9, PSI ~0.05 -> no alerts
python scripts/demo_closed_loop.py shift --factor 1.4   # DEMO ONLY: +40% demand in the last 28 days
python scripts/demo_closed_loop.py status            # ratio ~1.6, PSI ~0.7 -> ModelDegraded + DataDrift
./scripts/trigger_retrain.sh "DataDrift alert" production   # from the repo root, needs gh CLI
```

**Alertmanager → retrain (optional).** Alertmanager can call a webhook, but GitHub needs an authenticated request (`POST /repos/<owner>/<repo>/dispatches` with `{"event_type": "retrain"}`). That means putting a GitHub token inside the cluster, which is a security trade-off. So the demo uses `scripts/trigger_retrain.sh` run by a person. If you want it automated, use a fine-grained token limited to this repo, with only *Contents: read & write* (needed for dispatches), stored as a Kubernetes Secret in a small relay that Alertmanager calls only for alerts labelled `action: retrain`.

## ML supply-chain security

In an ML system, the *data* and the *model file* are part of what gets shipped, not just the code. Each step below has a check, and each check runs automatically.

| Step | Check | Where |
|---|---|---|
| Training data | `validate_data.py`: exact schema, whole-number quantities, 0/1 flags, no negatives, no duplicate (date, sku), ≤ 5% missing days, ≥ 90% of the previous row count, no product whose recent mean moved more than 3× or whose max exceeds 10× the previous p99. Drift (PSI > 0.25) is only a warning, because real demand change is why we retrain. | CI (against `main`'s profile), retrain workflow |
| Trained model | `check_model.py`: WAPE ≤ 20% and beats the naive forecast | Docker build, retrain workflow |
| Model file | Training writes `models/manifest.json` with the SHA-256 of the data, model and metrics. The API verifies the hashes **before unpickling** (pickle can run code), refuses a mismatch, keeps `/ready` at 503 (so the pod never gets traffic and the rollout fails), and sets `model_integrity_ok 0` (alert `ModelIntegrityFailed`). | API startup, container smoke test in CI |
| Image | Trivy scan → SBOM (Syft, SPDX JSON) → **cosign keyless signature** (GitHub OIDC, logged in Rekor) + signed SBOM attestation | `build-scan-push` |
| Deploy | `deploy.sh` runs `cosign verify` (signer must be *this repo's* `ci-cd.yml` on `main`) and `verify-attestation`, then deploys **by digest**. Unsigned image = nothing is applied. | `deploy-staging`, `deploy-production` |
| Pipeline | Every action is pinned to a full commit SHA with the version as a comment (`scripts/pin_actions.py`); Dependabot updates the pins | all workflows |

What each check does **not** cover (also in `docs/novelty.md`):
- Validation catches gross corruption: ×10, negatives, schema changes, truncation, duplicates. It does not catch subtle poisoning, such as ×2 on one product. The model gate and the business-KPI gate are the next lines of defence.
- The manifest alone does not stop someone who can rewrite both the model and the manifest. The image signature does.
- Keyless signing trusts GitHub's OIDC issuer and the Sigstore public-good infrastructure.

Manual deploy of an image you built locally (no signature): `VERIFY_SIGNATURES=false ./scripts/deploy.sh ...`. It prints a warning, and the pipeline never sets this.

## Access control and web hardening

| What | How |
|---|---|
| Accounts | `users` table, passwords hashed with **Argon2id**; `manager` and `viewer` are created on first start from `INITIAL_*_PASSWORD` (Kubernetes Secret) |
| Login | `POST /auth/login` returns a **JWT valid for 30 minutes** (HS256, `JWT_SECRET` from a Kubernetes Secret). The same 401 is returned for an unknown user and a wrong password, with the same timing. |
| Roles | `viewer` can read everything. `manager` can also create products, record deliveries and sales, backfill, and export sales (403 for a viewer). `/health` and `/ready` are public for the probes. |
| Brute force | 5 failed logins per client and username in 5 minutes → **429** with `Retry-After` (in memory, per pod). The client address is the **last** `X-Forwarded-For` entry, the one nginx adds, so a spoofed header does not reset the counter. |
| Production safety | With `APP_ENV=production`, the API refuses to start without `JWT_SECRET` and the two initial passwords |
| nginx | `/api/metrics`, `/api/docs`, `/api/redoc` and `/api/openapi.json` return 404 to the outside (Prometheus scrapes the backend Service inside the cluster). Strict **Content-Security-Policy** with `script-src 'self'` and no `unsafe-inline`, plus `X-Frame-Options`, `nosniff`, `Referrer-Policy` and `Permissions-Policy`. |
| Frontend | Login screen. The token is kept in `sessionStorage` (gone when the tab closes). Any 401 returns the user to the login screen. Write actions are hidden from viewers, and the API enforces this too. |
| Tests | `backend/tests/test_auth.py` (401 / 403 / 200, expired, forged, `alg: none` and other-key tokens, rate limit, spoofed `X-Forwarded-For`, Argon2 hash). Frontend: Vitest + Testing Library (`npm test`). |

## Security measures in this project

| Where | What |
|---|---|
| Code | SonarQube Cloud quality gate (bugs, vulnerabilities, code smells, coverage), mandatory on `main` |
| Dependencies | Trivy fs scan + `npm audit`; Dependabot opens update PRs weekly |
| Secrets | **Gitleaks over the full git history** + Trivy secret scan of the current files; passwords only in GitHub environment secrets → Kubernetes Secrets; JWT key generated inside the cluster; `.env` is git-ignored |
| Images | Multi-stage builds, slim bases, non-root users, Trivy image scan blocks HIGH/CRITICAL before push |
| Infrastructure as code | Trivy misconfig scan of Dockerfiles and Kubernetes manifests |
| Runtime | `runAsNonRoot`, read-only root filesystem, all capabilities dropped, no service-account token, resource limits, NetworkPolicy (Postgres reachable only from the backend) |
| Pipeline | Least-privilege `GITHUB_TOKEN` permissions; deploy jobs depend on every scan job, so a failed scan never deploys; smoke test with automatic rollback |

**Note on pinning actions:** In March 2026, attackers force-pushed most of the version tags of `aquasecurity/trivy-action` to point at credential-stealing code (CVE-2026-33634, advisory GHSA-69fq-xp46-6x23). That is why every action here is pinned to a commit SHA, which cannot be moved. The current pins are recorded in `.github/action-pins.json` (looked up with `git ls-remote` on 2026-11-22). Re-pin after an upgrade with `python scripts/pin_actions.py .github/action-pins.json`.

## Evaluation (what to measure and where it comes from)

| Metric | Source |
|---|---|
| Deployment time | GitHub Actions run duration (compare with timing a manual deploy) |
| Deployment success / failure rate | Actions run history |
| Vulnerabilities caught before deploy | Trivy and SonarQube reports |
| Test pass / failure rate | pytest report (`test-results.xml` artifact) |
| Availability | Prometheus `up` metric over time |
| Forecast accuracy | `models/forecast_model.metrics.json` (MAE, RMSE, WAPE, MAPE on the last 60 days, never seen in training) |
| Stockouts and expired stock | `python scripts/simulate.py --json kpis.json`: replays the 60 held-out days with three ordering policies and writes waste_rate, fill_rate, stockout_days and lost_sales per policy |

`simulate.py` compares:
- **replenish**: re-order whatever sold today,
- **baseline**: a moving-average rule with a 20% buffer,
- **ours**: forecast + FEFO + safety stock.

It reports lost sales, stockout days, expired units, fill rate and waste rate.

The simulation is **deterministic**: the dataset has a fixed seed and a fixed end date (`DEFAULT_END` in `generate_sales.py`), the model has a fixed `random_state`, and nothing reads the clock. Two runs of the same code give byte-identical JSON. That is what makes it usable as a CI gate. Without `--data`, it generates the dataset in memory, so it runs headless in CI with no files. The "ours" policy calls `app.inventory.plan_order`, the same function the API uses, so a bug in the live decision logic also shows up in the simulated KPIs.

**Be honest about the data.** The sales data is synthetic, generated with weekly seasonality, holidays, promotions and noise, so the project runs offline and the demo is repeatable. All inventory numbers are *simulated results on synthetic data*, not results from a real store. To use real data, replace `data/sales.csv` with any daily sales file that has the columns `date, sku, quantity, on_promo, is_holiday` (for example, a subset of the Kaggle "Corporacion Favorita" grocery dataset), and add the products to `app/catalog.py`.

## Known limitations

- Synthetic data. The model has not been tested on a real store.
- Promotion and holiday flags for future days are assumed to be 0 when forecasting.
- Sales history contains what was *sold*, not what was *demanded*. On stockout days, true demand is underestimated.
- Tables are created with `create_all` instead of migrations (Alembic would be the next step).
- The minikube setup runs on one node, so it shows self-healing, not high availability.

## Demo script (about 5 minutes)

1. Open the dashboard and walk through the REORDER, EXPIRY_RISK and OK cards, the forecast chart and the stock expiry colours.
2. Change something small (for example, the dashboard subtitle), push it, and show the pipeline running test → scan → build → deploy.
3. Show a blocked deploy: on a branch, add an old vulnerable package to `backend/requirements.txt` (for example, `jinja2==2.10`), open a PR, and show Trivy failing the pipeline.
4. Kill a pod: `kubectl -n freshtrack-prod delete pod -l app=backend --wait=false`. Kubernetes recreates it, and Grafana shows the dip.
5. Show the Grafana dashboard and an alert in Prometheus.
6. Show the evaluation table (pipeline metrics + simulation output).
