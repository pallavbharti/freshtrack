#!/usr/bin/env bash
set -euo pipefail

REASON="${1:?give a reason, e.g. the alert name}"
SOURCE="${2:-production}"

gh workflow run retrain.yml --ref main -f source="$SOURCE" -f reason="$REASON"
echo "retrain requested (source=$SOURCE). Waiting for the run to start..."
sleep 8
RUN_ID=$(gh run list --workflow retrain.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status
