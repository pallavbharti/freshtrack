#!/usr/bin/env bash
set -euo pipefail

NS="${1:?namespace required}"
TAG="${2:?image tag required}"
REPO="${REPO:-${GITHUB_REPOSITORY:-}}"
OWNER="${OWNER:-${GITHUB_REPOSITORY_OWNER:-${REPO%%/*}}}"
OWNER="${OWNER,,}"
VERIFY_SIGNATURES="${VERIFY_SIGNATURES:-true}"

if [[ -z "$OWNER" ]]; then
  echo "set OWNER to your GitHub username (and REPO=owner/repo for signature checks)" >&2
  exit 1
fi
for var in DB_PASSWORD MANAGER_PASSWORD VIEWER_PASSWORD; do
  if [[ -z "${!var:-}" ]]; then
    echo "$var is empty - add it as an environment secret in GitHub (or export it for a manual run)" >&2
    exit 1
  fi
done

cd "$(dirname "$0")/.."

declare -A IMAGE_REF
for svc in backend frontend; do
  ref="ghcr.io/${OWNER}/freshtrack-${svc}:${TAG}"
  if [[ "$VERIFY_SIGNATURES" == "false" ]]; then
    echo "!! WARNING: signature check skipped for $ref (VERIFY_SIGNATURES=false)"
    IMAGE_REF[$svc]="$ref"
    continue
  fi
  if [[ -z "$REPO" ]]; then
    echo "set REPO=owner/repo so the signer identity can be checked" >&2
    exit 1
  fi

  identity="^https://github.com/${REPO}/\.github/workflows/ci-cd\.yml@refs/heads/main$"
  echo ">> verifying signature of $ref"
  if ! out=$(cosign verify "$ref" \
        --certificate-identity-regexp "$identity" \
        --certificate-oidc-issuer https://token.actions.githubusercontent.com \
        --output json 2>/tmp/cosign.err); then
    echo "REFUSING TO DEPLOY: $ref has no valid signature from ${REPO} ci-cd.yml on main" >&2
    cat /tmp/cosign.err >&2
    exit 1
  fi
  digest=$(printf '%s' "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["critical"]["image"]["docker-manifest-digest"])')

  cosign verify-attestation "$ref" --type spdxjson \
    --certificate-identity-regexp "$identity" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com >/dev/null 2>/tmp/cosign.err \
    || { echo "REFUSING TO DEPLOY: no valid SBOM attestation for $ref" >&2; cat /tmp/cosign.err >&2; exit 1; }

  IMAGE_REF[$svc]="ghcr.io/${OWNER}/freshtrack-${svc}@${digest}"
  echo "   ok: ${IMAGE_REF[$svc]}"
done

echo ">> namespace $NS, version $TAG"
kubectl apply -f k8s/namespaces.yaml

kubectl -n "$NS" create secret generic db-credentials \
  --from-literal=password="$DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

if kubectl -n "$NS" get secret app-secrets >/dev/null 2>&1; then
  JWT_SECRET=$(kubectl -n "$NS" get secret app-secrets -o jsonpath='{.data.jwt-secret}' | base64 -d)
else
  JWT_SECRET=$(openssl rand -base64 48 | tr -d '\n')
fi
kubectl -n "$NS" create secret generic app-secrets \
  --from-literal=jwt-secret="$JWT_SECRET" \
  --from-literal=manager-password="$MANAGER_PASSWORD" \
  --from-literal=viewer-password="$VIEWER_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
unset JWT_SECRET

kubectl -n "$NS" apply -f k8s/postgres.yaml -f k8s/network-policy.yaml
kubectl -n "$NS" rollout status statefulset/postgres --timeout=180s

for svc in backend frontend; do
  sed "s#ghcr.io/OWNER/freshtrack-${svc}:latest#${IMAGE_REF[$svc]}#" "k8s/${svc}.yaml" \
    | kubectl -n "$NS" apply -f -
  kubectl -n "$NS" annotate deployment/"$svc" kubernetes.io/change-cause="deploy ${TAG}" --overwrite
done

kubectl -n "$NS" rollout status deployment/backend --timeout=240s
kubectl -n "$NS" rollout status deployment/frontend --timeout=120s

kubectl -n "$NS" get pods -o wide
