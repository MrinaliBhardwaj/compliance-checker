echo "Health:"
echo "Open http://localhost:8000/docs to explore the API"
#!/usr/bin/env bash
# Simple demo script: apply migrations, seed, start server in foreground,
# and show a quick health check. Requires postgres + redis running via docker-compose.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Applying migrations against REGIS_DATABASE_URL or default local Postgres..."
python -c "from alembic.config import Config; from alembic import command; import os; cfg=Config('alembic.ini'); url=os.getenv('REGIS_DATABASE_URL','postgresql+psycopg://regis:regis@localhost:5432/regis'); cfg.set_main_option('sqlalchemy.url',url); command.upgrade(cfg,'head')"

echo "Seeding library (idempotent)"
python -m app.seed.cli

echo "Starting uvicorn (foreground). Press Ctrl-C to stop."
uvicorn app.main:app --host 0.0.0.0 --port 8000
