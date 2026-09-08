#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(dirname "$(dirname "$0")")
cd "$ROOT_DIR"

echo "Starting dev services: postgres redis minio qdrant..."
docker compose up -d postgres redis minio qdrant

echo "Waiting for Postgres to be ready..."
for i in {1..60}; do
  docker compose exec -T postgres pg_isready -U regis && break || sleep 1
done

echo "Ensure regis_app role and regis_test DB exist..."
docker compose exec -T postgres bash -lc "psql -U regis -c \"CREATE ROLE regis_app WITH LOGIN PASSWORD 'regis_app_pw'\" || true"
docker compose exec -T postgres bash -lc "psql -U regis -c \"CREATE DATABASE regis_test OWNER regis_app\" || true"

echo "Apply alembic migrations to regis_test as regis_app..."
REGIS_TEST_PG_URL='postgresql+psycopg://regis_app:regis_app_pw@postgres:5432/regis_test'
docker compose run --rm api bash -lc "export REGIS_TEST_PG_URL='$REGIS_TEST_PG_URL' && alembic -c alembic.ini upgrade head"

echo "Run backend tests..."
docker compose run --rm api bash -lc "export REGIS_TEST_PG_URL='$REGIS_TEST_PG_URL' && pip install -e .[dev] && pytest -q"

echo "Dev run complete."