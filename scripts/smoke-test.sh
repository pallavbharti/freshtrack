#!/usr/bin/env bash
set -euo pipefail

NS="${1:?namespace required}"
: "${VIEWER_PASSWORD:?VIEWER_PASSWORD is required (the viewer account password)}"
PORT=$(( 18000 + RANDOM % 1000 ))

kubectl -n "$NS" port-forward svc/backend "$PORT":8000 >/dev/null 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null || true; rm -f /tmp/smoke.out' EXIT
sleep 4
BASE="http://localhost:${PORT}"

check() {
  local path=$1 expect=${2:-200}
  local code
  code=$(curl -s -o /tmp/smoke.out -w '%{http_code}' -H "Authorization: Bearer ${TOKEN:-}" "$BASE$path")
  if [[ "$code" != "$expect" ]]; then
    echo "FAIL $path -> HTTP $code (expected $expect)"
    head -c 500 /tmp/smoke.out; echo
    exit 1
  fi
  echo "ok   $path ($code)"
}

TOKEN=""
check /health
check /ready
check /products 401

TOKEN=$(curl -sf -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"viewer\",\"password\":\"${VIEWER_PASSWORD}\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
check /products
check /recommendations
check "/forecast/1?days=7"
echo "smoke test passed for $NS"
