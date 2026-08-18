# Regis backend — API and worker share one image; the command selects the role.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    REGIS_LOG_FORMAT=json

WORKDIR /app

# Build tooling lives only in this layer so it is not shipped in the runtime image.
FROM base AS deps
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
# Dependency resolution is cached on pyproject alone, so application edits do not
# re-resolve the tree.
RUN pip install --prefix=/install .

FROM base AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 regis
COPY --from=deps /install /usr/local
COPY --chown=regis:regis . /app

USER regis
EXPOSE 8000

# Hits the app's own health route, so an unhealthy container is one that cannot
# serve rather than one whose port happens to be open.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
