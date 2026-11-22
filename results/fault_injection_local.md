# Fault-injection results (local run, 2026-11-22 10:47 UTC)

Local run: stages execute one after another on one machine (on GitHub, jobs run in
parallel). Stages marked *not run* needed a tool that was not available; a fault
that only those stages could catch is reported as not caught *by the stages that ran*.

| Fault | Basic pipeline | Full pipeline |
|---|---|---|
| control | ok (no alarm) | ok (no alarm) |
| vuln-dependency | not caught by the stages that ran | not caught by the stages that ran |
| hardcoded-secret | yes - trivy-secret (7.1 s) | yes - trivy-secret (13.5 s) |
| failing-test | yes - unit-tests (7.1 s) | yes - unit-tests (7.4 s) |
| model-degradation | not caught by the stages that ran | yes - business-gate (11.8 s) |
| expiry-policy-bug | not caught by the stages that ran | yes - business-gate (14.3 s) |
| root-container | not caught by the stages that ran | yes - trivy-misconfig (16.9 s) |
| tampered-model | not caught by the stages that ran | not caught by the stages that ran |
| poisoned-data | not caught by the stages that ran | yes - data-validation (0.4 s) |

- **basic**: caught 2 of 8 faults before deploy (25%)
- **full**: caught 6 of 8 faults before deploy (75%)
