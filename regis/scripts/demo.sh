#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(dirname "$(dirname "$0")")
cd "$ROOT_DIR"

echo "Demo: probing API endpoints (health, ready, metrics)"

for i in {1..60}; do
  if curl -sfS http://localhost:8000/ready >/dev/null 2>&1; then
    break
  fi
  echo "waiting for api... ($i)"
  sleep 1
done

echo "/health";
curl -sS http://localhost:8000/health || true; echo

echo "/ready";
curl -sS http://localhost:8000/ready || true; echo

echo "/metrics (first 20 lines)";
curl -sS http://localhost:8000/metrics | head -n 20 || true; echo

echo "OpenAPI summary (first 200 chars):"
curl -sS http://localhost:8000/openapi.json | head -c 200 || true; echo

echo "Demo complete."
