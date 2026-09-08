#!/usr/bin/env bash
# One command to get Regis running locally for a demo.
#
#   ./scripts/run_local.sh
#
# Installs backend deps, creates and seeds a SQLite database, then starts the
# API on :8000 and the UI on :3000. Ctrl-C stops both. Re-running is safe —
# the seed is an idempotent upsert and the database is reused unless you pass
# --fresh.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # -> regis/
FRESH=0
[[ "${1:-}" == "--fresh" ]] && FRESH=1

export REGIS_DATABASE_URL="sqlite+pysqlite:///dev.db"
export REGIS_JWT_SECRET="${REGIS_JWT_SECRET:-dev-secret-change-me}"
export REGIS_CONTENT_ADMIN_EMAILS="${REGIS_CONTENT_ADMIN_EMAILS:-demo@regis.example}"

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { echo "ERROR: $PY not found. Install Python 3.11+."; exit 1; }
command -v npm >/dev/null || { echo "ERROR: npm not found. Install Node 18+."; exit 1; }
echo "Using $("$PY" --version) and npm $(npm --version)"

# --- backend -----------------------------------------------------------------
cd backend
echo
echo "[1/4] Installing backend dependencies…"
"$PY" -m pip install -e ".[dev]" --quiet --disable-pip-version-check

if [[ $FRESH -eq 1 ]]; then rm -f dev.db; echo "      (--fresh: removed dev.db)"; fi

echo "[2/4] Creating and seeding the database…"
"$PY" -m app.seed.cli --create-all

echo "[3/4] Starting the API on http://localhost:8000 …"
"$PY" -m uvicorn app.main:app --port 8000 --log-level warning &
API_PID=$!
cd ..

cleanup() {
  echo
  echo "Stopping…"
  kill "$API_PID" 2>/dev/null || true
  kill "${UI_PID:-}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for i in $(seq 1 40); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then break; fi
  if ! kill -0 "$API_PID" 2>/dev/null; then echo "ERROR: the API exited during startup."; exit 1; fi
  sleep 1
done
curl -sf http://localhost:8000/health >/dev/null || { echo "ERROR: API did not become healthy."; exit 1; }
echo "      API is up."

# --- frontend ----------------------------------------------------------------
cd frontend
echo "[4/4] Installing frontend dependencies (first run takes a minute)…"
# npm ci when the lockfile is usable: it is faster and, unlike npm install,
# leaves package-lock.json untouched (some npm versions rewrite unrelated
# fields in it, which shows up as spurious repo churn).
if [[ -f package-lock.json ]] && npm ci --silent --no-audit --no-fund 2>/dev/null; then
  :
else
  npm install --silent --no-audit --no-fund
fi
echo
echo "Starting the UI on http://localhost:3000 …"
npm run dev &
UI_PID=$!
cd ..

for i in $(seq 1 60); do
  curl -sf http://localhost:3000 >/dev/null 2>&1 && break
  sleep 1
done

cat <<'BANNER'

────────────────────────────────────────────────
  Regis is running.

    UI    http://localhost:3000
    API   http://localhost:8000/docs

  Sign up on the landing page, then complete the
  three-step compliance profile to generate a
  calendar. Ctrl-C here stops both servers.
────────────────────────────────────────────────
BANNER

wait "$UI_PID"
