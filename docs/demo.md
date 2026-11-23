# 6-minute demo script

**Before the demo (the day before):**
- Pipeline green on `main`, staging and production deployed, Grafana open, logged in to GitHub.
- Run the fault experiment once on GitHub, so its table is ready for part (d).
- Prepare the branches for part (a) and (b): `./scripts/inject_fault.sh expiry-policy-bug` and `./scripts/inject_fault.sh tampered-model`. Push both the day before, so their runs are finished and you can show them instantly.
- Terminals open: (1) repo root, (2) `backend/` with the venv active, (3) a port-forward to staging: `kubectl -n freshtrack-staging port-forward svc/backend 18000:8000`.
- Browser tabs: dashboard (`minikube service frontend -n freshtrack-prod`), GitHub Actions, Grafana dashboard "FreshTrack", Prometheus Alerts page.

Everything shown is **simulated on synthetic data**. Say so once at the start.

---

### 0:00 – 0:40 · The problem (talk, no typing)
> "Every team here built a pipeline that checks whether code works and is secure. A grocery store cares about something else: does this change make us **throw away more food** or **run out of milk**? Our pipeline checks that before deploy, keeps checking after deploy, and we measured it against a generic pipeline with 8 injected faults."

Show the dashboard for 10 seconds: REORDER / EXPIRY_RISK cards, forecast chart, viewer vs manager login.

### 0:40 – 2:10 · (a) Passes every unit test, blocked by the business gate
1. Show the diff of `fault/expiry-policy-bug` on GitHub: one line, `cover = window  # order a full week at once to avoid stockouts`.
   > "Looks like a sensible idea: order a week at once and you never run out."
2. Open its **CI basic** run: all green.
   > "A normal pipeline would ship this."
3. Open its **CI/CD** run → *Backend lint + tests*: green (all unit tests pass) → *Business-KPI gate*: **red**. Open the job summary: the KPI table shows waste **0.27% → 61%**.
   > "Every unit test passed. The gate replayed 60 days of sales with this code and saw that most of the milk and spinach would expire. Build and deploy never ran."

Backup, live in terminal 2 (about 15 s): `git checkout fault/expiry-policy-bug && python scripts/policy_gate.py; git checkout main`

### 2:10 – 3:10 · (b) A tampered model is refused
1. Show the diff of `fault/tampered-model`: the Dockerfile appends bytes to the model *after* it was trained and hashed.
   > "This simulates a compromised build step."
2. **CI basic** run: green, so the image would be pushed.
3. **CI/CD** run → *Build, test, scan, sign image (backend)* → step *Container smoke test*: `/ready -> 503 {"status":"model integrity check failed", ...}`.
   > "The API checks the model against the SHA-256 manifest written at training, **before** loading it, because pickle files can run code. A tampered model never gets traffic, never gets pushed, and is never signed, and `deploy.sh` refuses unsigned images."

Backup, live in terminal 2: `printf x >> models/forecast_model.joblib && uvicorn app.main:app --port 8001` and, in another terminal, `curl localhost:8001/ready`. Then restore the file with `python scripts/train_model.py`.

### 3:10 – 4:50 · (c) Drift alert → retrain
In terminal 2, against staging:
```bash
python scripts/demo_closed_loop.py --base-url http://localhost:18000 backfill
python scripts/demo_closed_loop.py --base-url http://localhost:18000 status
#  ratio ~0.9, median PSI ~0.05 -> no alerts
python scripts/demo_closed_loop.py --base-url http://localhost:18000 shift --factor 1.4
python scripts/demo_closed_loop.py --base-url http://localhost:18000 status
#  ratio ~1.6 (ModelDegraded), PSI ~0.7 (DataDrift), bias ~ -27%
```
(Use `MANAGER_PASSWORD=...` for staging.)
1. Grafana: the *Store: live WAPE / held-out WAPE* and *median PSI* panels jump above their threshold lines.
2. Prometheus → Alerts: `DataDrift` / `ModelDegraded` are pending, then firing. Mention the `for:` durations. If you do not want to wait during the demo, show the promtool test in the CI logs instead.
   > "The thresholds 1.45 and 0.25 were measured, not guessed: on normal weeks the ratio never went above 1.42."
3. Terminal 1: `./scripts/trigger_retrain.sh "DataDrift alert" production`. Show the run: export → **data validation** → train → **model check** → **business gate** → PR opened.
   > "The retrained model goes through exactly the same gates as a code change, and a human merges it."

Explain why there is no automatic webhook in one sentence: putting a GitHub token in the cluster is a trade-off; README shows how to do it safely.

### 4:50 – 5:40 · (d) Fault-injection table
Show `results/fault_injection_github.md` (or the slide built from it): 8 faults + control, generic vs FreshTrack, the stage that caught each, and time to detection.
> "The control run raised no alarm in either pipeline. The generic pipeline missed the faults that are about the **business, the data and the model**. Ours stopped them before deploy."

Be explicit about what is local vs GitHub, and about any fault that was not caught.

### 5:40 – 6:00 · Close
> "What is new is not a new algorithm: it is joining business KPIs, ML supply-chain checks and a monitored retrain loop into one delivery pipeline for perishable inventory. The limitations are on the last slide: synthetic data, thresholds calibrated on it, and our policy is about as good as a good rule of thumb, which the gate protects but does not prove."

---

## If something breaks live
| Problem | Fallback |
|---|---|
| Runner offline / cluster down | Show the finished runs from the day before (Actions history) |
| Alerts still pending | Show the promtool unit test output in the *Alert rules check* job |
| Port-forward dies | Run the demo script against a local API: `uvicorn app.main:app` + default URL |
| Wi-Fi blocks GitHub | Screenshots of each step, prepared in advance |
