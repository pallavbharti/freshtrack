#!/usr/bin/env bash
set -euo pipefail

NS="${1:?namespace required}"
OUT="${2:?output file required}"
: "${MANAGER_PASSWORD:?MANAGER_PASSWORD is required (export is manager-only)}"
PORT=$(( 19000 + RANDOM % 1000 ))

kubectl -n "$NS" port-forward svc/backend "$PORT":8000 >/dev/null 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null || true' EXIT
sleep 4

BASE="http://localhost:${PORT}"
TOKEN=$(curl -sf -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"manager\",\"password\":\"${MANAGER_PASSWORD}\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -sSf -H "Authorization: Bearer $TOKEN" "$BASE/sales/export?days=730" -o "$OUT"
echo "exported $(($(wc -l < "$OUT") - 1)) rows from $NS to $OUT"
