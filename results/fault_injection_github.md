# Fault-injection results (github run, 2026-11-24 20:16 UTC)

| Fault | Basic pipeline | Full pipeline |
|---|---|---|
| vuln-dependency | yes - Lint + unit tests / Run pytest --cov=app --cov=scripts --cov-report=xml:coverage.xml (48 s) | yes - Backend lint + tests + model check / Lock files match pinned requirements (27 s) |
| failing-test | yes - Lint + unit tests / Run pytest --cov=app --cov=scripts --cov-report=xml:coverage.xml (77 s) | yes - Backend lint + tests + model check / Tests (78 s) |
| hardcoded-secret | yes - SonarQube + Trivy (default scanners) / SonarQube Cloud scan (219 s) | yes - Static analysis (SonarQube Cloud + Gitleaks + Trivy fs) / SonarQube Cloud scan (205 s) |
| root-container | yes - SonarQube + Trivy (default scanners) / SonarQube Cloud scan (160 s) | yes - Static analysis (SonarQube Cloud + Gitleaks + Trivy fs) / SonarQube Cloud scan (210 s) |
| poisoned-data | yes - Build + image scan (backend) / Run docker/build-push-action@c3c9e263c25d99ce0380d002d59b67737d91b0dc (230 s) | yes - Backend lint + tests + model check / Validate training data against main (34 s) |
| model-degradation | no | yes - Business-KPI gate (waste / fill rate) / Run business-KPI gate (113 s) |
| expiry-policy-bug | no | yes - Business-KPI gate (waste / fill rate) / Run business-KPI gate (127 s) |
| control | ok (no alarm) | ok (no alarm) |
| tampered-model | no | yes - Build, test, scan, sign image (backend) / Container smoke test (356 s) |

- **basic**: caught 5 of 8 faults before deploy (62%)
- **full**: caught 8 of 8 faults before deploy (100%)
