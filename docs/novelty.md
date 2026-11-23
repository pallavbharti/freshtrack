# What is new in FreshTrack

> Every claim is tagged **[literature-supported]** (a published source says it; cite it from our Source Pack where it says `[CITE: …]`) or **[inferred]** (our own reasoning or our own measurement). Every number comes from a real run of the code in this repository, on **synthetic data**, unless it is labelled *expected*.

## 1. Novelty statement

Secure CI/CD is now standard practice: automated tests, static analysis, dependency and container scanning, and automated deployment **[literature-supported]** `[CITE: Source Pack – DevSecOps / secure CI/CD papers]`. Monitoring deployed ML models for data drift and degraded accuracy is also established **[literature-supported]** `[CITE: Source Pack – MLOps / ML monitoring papers]`. In our literature review we found **limited work that joins these with business-level outcome checks for perishable-food inventory**: deployment gates that ask whether a change makes a store *waste more food or run out of stock more often*, followed by a closed loop that watches the same question after deployment **[inferred – from our review; state the search terms and databases in the report]**.

FreshTrack's contribution is that integration, not a new algorithm:

1. **A business-KPI deployment gate.** Every change replays 60 held-out days with the candidate code and model. If the simulated waste rate, fill rate, stockouts or forecast error get worse than on `main`, the change cannot be built or deployed.
2. **A closed loop after deployment.** Live forecast error, bias and data drift are measured against real sales. Alerts can start a retrain, and the retrained model passes through *the same* gates plus data validation before a human merges it.
3. **ML supply-chain checks.** Training data is validated, the model is bound to its data and metrics by SHA-256 hashes, images are signed keylessly with an SBOM attestation, and deploys verify signatures and deploy by digest.
4. **Evidence by fault injection.** 8 realistic faults plus a control run through a generic pipeline and through ours.

We do **not** claim a new forecasting method, a new inventory policy, or that no related work exists.

## 2. Generic CI/CD vs FreshTrack

| Capability | Generic CI/CD (`ci-basic.yml`) | FreshTrack (`ci-cd.yml`) | Tag |
|---|---|---|---|
| Lint, unit tests, SonarQube | ✅ | ✅ | literature-supported (standard practice) |
| Known-vulnerable dependencies (Trivy fs) | ✅ | ✅ | literature-supported |
| Secrets in current files (Trivy) | ✅ | ✅ | literature-supported |
| Secrets anywhere in git history (Gitleaks) | ❌ | ✅ | literature-supported (tooling practice) |
| Dockerfile / Kubernetes misconfiguration (Trivy misconfig) | ❌ (not in Trivy's default scanners) | ✅ | literature-supported |
| Image vulnerability scan | ✅ | ✅ | literature-supported |
| Model quality gate on the shipped artifact (WAPE, beats naive) | ❌ | ✅ | literature-supported `[CITE: ML testing]` |
| **Business-KPI gate** (simulated waste, fill rate, stockouts vs `main`) | ❌ | ✅ | **inferred** (our contribution) |
| Training-data validation against the previous dataset | ❌ | ✅ | literature-supported `[CITE: data validation for ML]` |
| Model integrity (SHA-256 manifest, verified before unpickling) | ❌ | ✅ | inferred (design) |
| Container smoke test before push | ❌ | ✅ | literature-supported (common practice) |
| SBOM + keyless signature + verify before deploy, deploy by digest | ❌ | ✅ | literature-supported `[CITE: Sigstore / SLSA]` |
| Actions pinned to commit SHAs | ❌ | ✅ | literature-supported (the March 2026 trivy-action tag hijack, CVE-2026-33634, GHSA-69fq-xp46-6x23) |
| Live forecast error / bias / drift metrics and alerts | ❌ | ✅ | literature-supported `[CITE: ML monitoring]` |
| **Alert → retrain → same gates → reviewed PR** | ❌ | ✅ | **inferred** (our contribution) |
| Auth with roles, rate-limited login, CSP, internal endpoints blocked | — (app-level, not pipeline) | ✅ | literature-supported (OWASP practice) |

## 3. Evidence (real runs, synthetic data)

### 3.1 Forecast model (60 held-out days)
| | WAPE |
|---|---|
| Our model (calendar flags known) | 15.43% |
| Our model, as served (promo/holiday unknown, like the live API) | 17.89% |
| Naive "same day last week" | 25.37% |

### 3.2 Ordering policies (simulated, 60 days, 8 products)
| Policy | Waste rate | Fill rate | Stockout days | Lost sales |
|---|---|---|---|---|
| Re-order what sold | 0.000% | 93.08% | 94 | 917 |
| Moving-average rule (+20%) | 0.243% | 99.53% | 4 | 63 |
| **Ours** | 0.273% | 99.53% | 4 | 63 |

**Honest reading [inferred]:** on this synthetic data, our policy is clearly better than "re-order what sold" and about equal to a sensible moving-average rule. Its waste is slightly higher (+4 units, all of it spinach, which has a 2-day shelf life). The stockouts happen on the same early days for both, before the first order can arrive. The gate therefore requires our policy to be *no worse than the baseline within a tolerance*, not strictly better. The synthetic demand is regular, and real data with more noise is needed to show whether the ML forecast pays off.

### 3.3 Business gate vs unit tests
| Change | Unit tests | Business gate |
|---|---|---|
| Order a full week at once, ignoring shelf life | all 113 backend tests pass | **fail**: waste 0.273% → 61.06% |
| Model 300 → 40 trees ("faster build") | pass (fixture WAPE 18.73% < 20%) | **fail**: waste 0.273% → 0.397% (vs-main tolerance 0.1 pp) |

### 3.4 Closed loop (live API, demo shift injected)
| | Live / held-out WAPE | Median PSI | Store bias |
|---|---|---|---|
| After deploy (backfilled 14 days) | 0.86 | 0.052 | +2.45% |
| After +40% demand in the last 28 days (demo) | **1.58** → ModelDegraded | **0.735** → DataDrift | **−26.9%** → ForecastBiased |

### 3.5 Threshold calibration (measured before choosing)
- **PSI:** per-product PSI on 28 daily values was too noisy (normal windows reached 0.5+). The median across products stayed ≤ **0.134** in normal windows, and was ≥ **0.325** after a ±25% shift. Threshold: **0.25**.
- **Live/held-out WAPE (store level):** normal 7-day windows peaked at **1.42 / 1.33 / 1.20** on 3 synthetic datasets. A degraded model or a +40% shift was at least **1.49 / 1.61 / 1.68**. Threshold: **1.45**. The margin is narrow (1.42 vs 1.49), so recalibrate on real data **[inferred]**.
- **Bias:** normal store bias was between −3.1% and +6.8%. Threshold: ±15%.
- A +25% shift does not trip ModelDegraded (lag features adapt), but DataDrift does. The two alerts complement each other **[inferred]**.

### 3.6 Data validation (`validate_data.py`)
Blocked: ×10 poisoning of one product, negative quantities, duplicate rows, a renamed column, a truncated file, and a mean collapse to 0. Allowed: a real +40% demand shift (that is what retraining is for).

### 3.7 Model integrity
API started with a model file that has 1 extra byte: `/ready` → 503, `/forecast` → 503, `model_integrity_ok 0`, log line "REFUSING to load model". Unsigned image: `deploy.sh` refuses, and makes 0 `kubectl` calls.

### 3.8 Fault injection (`results/fault_injection_*.csv`)
**Local run** (this machine; the vulnerability DB, Docker and SonarQube were not available):

| Fault | Generic | FreshTrack |
|---|---|---|
| control | no alarm | no alarm |
| vulnerable dependency | not run here | not run here |
| hard-coded secret | Trivy secret | Trivy secret (+ Gitleaks) |
| failing unit test | unit tests | unit tests |
| model degradation | not caught by stages that ran | business gate |
| expiry policy bug | not caught by stages that ran | business gate |
| root / privileged container | not caught by stages that ran | Trivy misconfig |
| tampered model | not run here (needs Docker) | not run here |
| poisoned data | not caught by stages that ran | data validation |

Of the stages that could run locally: generic 2/8, FreshTrack 6/8. **Final numbers come from the GitHub run** (`results/fault_injection_github.csv`). *Expected* there: the generic pipeline catches 3/8 (adds the vulnerable dependency) and FreshTrack catches 8/8 (adds the vulnerable dependency and the tampered model). SonarQube might also flag the root container in the generic pipeline; that is not measured yet.

## 4. Limitations

- **Synthetic data.** Every inventory and drift number is simulated. Thresholds were calibrated on synthetic data and must be recalibrated on real sales.
- **Our policy ≈ a good rule of thumb here**, not clearly better. The gate protects against regressions; it does not prove the ML is worth it.
- **Gates have tolerances.** Feature changes that move WAPE by under 2 points (for example, dropping `lag_7` and `lag_14`: +0.24 pp) pass every gate.
- **Data validation catches gross corruption, not subtle poisoning** (for example, ×2 on one product).
- **The manifest alone does not stop an attacker who can rewrite both files.** The image signature covers that, and it trusts GitHub OIDC and the public Sigstore infrastructure.
- **Login rate limiting is per pod and in memory.** It does not replace a WAF.
- **Promo and holiday flags are unknown for future days**, so live accuracy is lower than the training-time accuracy (17.89% vs 15.43%).
- **Sales are a censored view of demand.** On stockout days, true demand is underestimated.
- **The minikube setup is a single node.** It shows self-healing, not high availability.

## 5. Sources to check in the Source Pack

Replace each `[CITE: …]` above with entries from our Source Pack. Commonly cited works in these areas that the team may want to check (verify each one before citing; do not cite from this list without reading it):
- Sculley et al., "Hidden Technical Debt in Machine Learning Systems", NeurIPS 2015 (ML systems and monitoring)
- Breck et al., "The ML Test Score: A Rubric for ML Production Readiness and Technical Debt Reduction", IEEE Big Data 2017 (ML testing, data and model checks)
- Newman, Meyers, Torres-Arias, "Sigstore: Software Signing for Everybody", ACM CCS 2022 (keyless signing)
- SLSA framework, slsa.dev (supply-chain levels)
- GitHub advisory GHSA-69fq-xp46-6x23 / CVE-2026-33634 (trivy-action tag compromise, March 2026)
