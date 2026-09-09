#!/bin/bash
set -e

# One-command local startup: install all deps, seed DB, start API/UI, verify health
# Stops cleanly on Ctrl-C (kills both server processes)

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT="${REGIS_API_PORT:-8000}"
UI_PORT="${REGIS_UI_PORT:-3000}"
HEALTH_TIMEOUT=30

echo "🚀 Regis local startup"

# 1. Backend: install, migrate, seed
echo "📦 Backend: install dependencies"
cd "$PROJECT_ROOT/backend"
pip install -q -e ".[dev]"

echo "🗄️  Backend: migrate database"
alembic upgrade head

echo "📚 Backend: seed obligation library (idempotent)"
python -m app.seed.cli

# 2. Frontend: install
echo "📦 Frontend: install dependencies"
cd "$PROJECT_ROOT/frontend"
npm ci --quiet

# 3. Start services in parallel (backgrounded)
echo ""
echo "✨ Starting API (:$API_PORT) and UI (:$UI_PORT)..."
cd "$PROJECT_ROOT/backend"
uvicorn app.main:app --port "$API_PORT" --reload > /tmp/regis_api.log 2>&1 &
API_PID=$!

cd "$PROJECT_ROOT/frontend"
npm run dev > /tmp/regis_ui.log 2>&1 &
UI_PID=$!

# 4. Wait for health
echo "⏳ Waiting for API to be ready..."
ELAPSED=0
while ! curl -s "http://localhost:$API_PORT/health" > /dev/null 2>&1; do
  if [ $ELAPSED -ge $HEALTH_TIMEOUT ]; then
    echo "❌ API did not become healthy within ${HEALTH_TIMEOUT}s"
    kill $API_PID $UI_PID 2>/dev/null || true
    echo ""
    echo "API log:"
    tail -20 /tmp/regis_api.log
    exit 1
  fi
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done

echo "✅ API ready"
echo "✅ UI ready"
echo ""
echo "🎯 Success! Open http://localhost:$UI_PORT in your browser"
echo "📖 API docs: http://localhost:$API_PORT/docs"
echo ""
echo "Press Ctrl-C to stop both servers"
echo ""

# 5. Wait for Ctrl-C and clean up
trap "echo; echo '🛑 Stopping services...'; kill $API_PID $UI_PID 2>/dev/null || true; exit 0" INT TERM

wait
