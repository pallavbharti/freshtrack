#!/usr/bin/env bash
set -euo pipefail

FAULTS="control vuln-dependency hardcoded-secret failing-test model-degradation expiry-policy-bug root-container tampered-model poisoned-data"
FAULT="${1:?usage: inject_fault.sh <fault> [base-ref]   (or: list)}"
BASE="${2:-main}"

if [[ "$FAULT" == "list" ]]; then
  tr ' ' '\n' <<< "$FAULTS"
  exit 0
fi
[[ " $FAULTS " == *" $FAULT "* ]] || { echo "unknown fault: $FAULT (try: list)" >&2; exit 1; }

cd "$(git rev-parse --show-toplevel)"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "working tree not clean - commit or stash first" >&2
  exit 1
fi

PY="$(command -v python3 || command -v python)"
BRANCH="fault/${FAULT}"
git checkout -q -B "$BRANCH" "$BASE"

patch_once() {
  "$PY" - "$1" "$2" "$3" <<'EOF'
import sys
path, old, new = sys.argv[1:4]
text = open(path, encoding="utf-8").read()
if text.count(old) != 1:
    sys.exit(f"{path}: expected exactly one match for the patch, found {text.count(old)}")
open(path, "w", encoding="utf-8", newline="\n").write(text.replace(old, new))
EOF
}

case "$FAULT" in
  control)
    MSG="no change (control run)"
    echo "" >> README.md
    ;;

  vuln-dependency)
    echo "jinja2==2.10" >> backend/requirements.txt
    MSG="add a dependency with known vulnerabilities (jinja2==2.10)"
    ;;

  hardcoded-secret)
    mkdir -p backend/app/keys
    openssl genrsa 2048 2>/dev/null > backend/app/keys/dev-signing-key.pem
    MSG="commit a private key into the source tree"
    ;;

  failing-test)
    patch_once backend/app/inventory.py "    if left <= soon_days:" "    if left < soon_days:"
    MSG="off-by-one in expiry_status (breaks a unit test)"
    ;;

  model-degradation)
    patch_once backend/app/ml/forecaster.py "n_estimators=300," "n_estimators=40,"
    MSG="cut the model from 300 to 40 trees to speed up builds"
    ;;

  expiry-policy-bug)
    patch_once backend/app/inventory.py "    cover = min(lead_time_days + 1, window)" "    cover = window"
    MSG="order a full week of stock at once, ignoring shelf life"
    ;;

  root-container)
    patch_once backend/Dockerfile $'\nUSER app\n' $'\n'
    patch_once k8s/backend.yaml "            allowPrivilegeEscalation: false" "            privileged: true
            allowPrivilegeEscalation: true"
    patch_once k8s/backend.yaml $'        runAsNonRoot: true\n        seccompProfile:\n          type: RuntimeDefault\n      containers:\n        - name: backend' $'        runAsNonRoot: false\n        seccompProfile:\n          type: RuntimeDefault\n      containers:\n        - name: backend'
    MSG="run the backend as root in a privileged pod"
    ;;

  tampered-model)
    patch_once backend/Dockerfile " && python scripts/check_model.py models/forecast_model.metrics.json" " && python scripts/check_model.py models/forecast_model.metrics.json
RUN printf 'tampered' >> models/forecast_model.joblib"
    MSG="model file modified after training (supply-chain tampering)"
    ;;

  poisoned-data)
    "$PY" - <<'EOF'
import pandas as pd
df = pd.read_csv("backend/data/sales.csv")
m = (df["sku"] == "MLK-001") & (df["date"] >= sorted(df["date"].unique())[-60])
df.loc[m, "quantity"] = df.loc[m, "quantity"] * 10
df.to_csv("backend/data/sales.csv", index=False, lineterminator="\n")
EOF
    (cd backend && "$PY" scripts/validate_data.py data/sales.csv --write-profile data/profile.json >/dev/null)
    MSG="poison the training data (milk x10) and regenerate its profile"
    ;;
esac

git add -A
git commit -q -m "FAULT ${FAULT}: ${MSG}"
echo "created branch ${BRANCH}: ${MSG}"
echo "go back with: git checkout ${BASE}"
