# Fault catalogue

Each fault is one small, realistic change on its own branch, made by:

```bash
./scripts/inject_fault.sh <fault>        # creates branch fault/<fault> from main
./scripts/inject_fault.sh list
```

`scripts/run_fault_experiment.py` runs every fault through the **basic** pipeline (`ci-basic.yml`: lint, unit tests, SonarQube, Trivy with default scanners, build and image scan) and the **full** pipeline (`ci-cd.yml`). It records which stage stopped it and how long that took.

The "expected" columns below are our **prediction** before running. Measured results are in `results/fault_injection_*.csv`, and only those numbers go into the report.

| # | Fault | What changes | Why it is realistic | Expected: basic | Expected: full |
|---|---|---|---|---|---|
| 0 | `control` | nothing (a blank line in README) | checks for false alarms | passes | passes |
| 1 | `vuln-dependency` | adds `jinja2==2.10` to `backend/requirements.txt` | copying an old pin from a tutorial | caught: Trivy fs (vuln) | caught: Trivy fs (vuln) |
| 2 | `hardcoded-secret` | commits a freshly generated RSA private key (`backend/app/keys/dev-signing-key.pem`, never used) | "temporary" dev key committed by mistake | caught: Trivy fs (secret) | caught: Trivy fs (secret), Gitleaks |
| 3 | `failing-test` | `left <= soon_days` → `left < soon_days` in `expiry_status` | off-by-one | caught: unit tests | caught: unit tests |
| 4 | `model-degradation` | `n_estimators=300` → `40` | "speed up the build" | **missed**: the WAPE on the test fixture is 18.7%, under the absolute limit of 20% | caught: business-KPI gate (WAPE and waste vs main) |
| 5 | `expiry-policy-bug` | order cover = whole 7-day window instead of lead time + 1 | "order a week at once to avoid stockouts", ignoring shelf life | **missed**: every unit test passes | caught: business-KPI gate (simulated waste 0.27% → 61%) |
| 6 | `root-container` | removes `USER app` from the Dockerfile; pod `privileged: true`, `runAsNonRoot: false` | debugging a permission error the quick way | **missed**: Trivy's default scanners do not check config (SonarQube might raise a hotspot, to be measured) | caught: Trivy misconfig |
| 7 | `tampered-model` | a build step appends bytes to the model after it was trained and hashed | compromised build step or base-image layer | **missed**: the image builds, scans clean and is pushed | caught: container smoke test (model refused, `/ready` 503) |
| 8 | `poisoned-data` | milk sales ×10 for the last 60 days, and the attacker regenerates `profile.json` | poisoned or corrupted data export | **missed**: tests and scans pass (to be measured) | caught: data validation against `main`'s profile |

## How faults 4 and 5 were chosen (measured, synthetic data)

The brief suggested "drop lag features" for fault 4. We measured it first:

| Change | WAPE on main data | WAPE on unit-test fixture | Caught by |
|---|---|---|---|
| drop all lag/rolling features | much worse | above 20% | unit tests (both pipelines) |
| drop `lag_7`, `lag_14` | 15.67% (+0.24) | 16.50% | nothing, because the change is too small to matter |
| drop `day_of_week`, `is_weekend` | 17.17% (+1.74) | 18.12% | nothing (below the 2 pp tolerance) |
| `n_estimators` 300 → 40 | 16.93% (+1.50) | 18.73% | business-KPI gate: waste 0.27% → 0.40% |

So fault 4 uses the tree-count change. It passes the absolute unit-test threshold but worsens the business KPIs. Partial feature drops that move WAPE by less than 2 points are **not** caught by any gate. That is a known tolerance, not a hidden one.

## Running it

```bash
# real experiment on GitHub (needs: gh auth login, Actions enabled, SONAR_TOKEN set)
python scripts/run_fault_experiment.py --mode github

# local approximation (stages that need missing tools are reported as "not run")
TRIVY_BIN=/path/to/trivy GITLEAKS_BIN=/path/to/gitleaks python scripts/run_fault_experiment.py --mode local
```

If you cannot use the script, do it by hand for each fault:

1. `./scripts/inject_fault.sh <fault>`, then `git push -f origin fault/<fault>`, then `git checkout main`
2. Open the Actions tab. Two runs start for that commit: **CI/CD** and **CI basic (comparison)**.
3. For each run, note the first job that failed (and the failing step), and the time from the run's start to that job's end.
4. Fill in `results/fault_injection_template.csv`.

Delete the fault branches afterwards: `git push origin --delete fault/<fault>`.
