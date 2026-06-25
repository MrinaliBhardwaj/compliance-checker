"""
Application settings (pydantic-settings). Env-driven; safe dev defaults.

Data residency note: in production every managed service (RDS, ElastiCache, S3,
Bedrock/Anthropic endpoint) is pinned to AWS ap-south-1 — see infra/terraform.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env next to the backend root (…/backend/.env) so the app loads its
# config regardless of the process working directory (e.g. when launched from the
# repo root by the preview runner). Explicit env vars still take precedence.
_BACKEND_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REGIS_", env_file=str(_BACKEND_ENV), extra="ignore")

    env: str = "dev"  # dev | staging | prod
    # Postgres in every real environment; SQLite only for local engine/integration tests.
    database_url: str = "postgresql+psycopg://regis:regis@localhost:5432/regis"
    redis_url: str = "redis://localhost:6379/0"

    # AWS / storage (ap-south-1)
    aws_region: str = "ap-south-1"
    s3_bucket: str = "regis-evidence-dev"

    # AI
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"  # PRD: Sonnet for all V1 AI
    qdrant_url: str = "http://localhost:6333"

    # Notifications
    slack_webhook_url: str | None = None
    email_from: str = "compliance@regis.app"

    # Auth
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 12

    # Field-level encryption key (Fernet). Required outside dev.
    field_key: str | None = None

    def assert_production_ready(self) -> None:
        if self.env != "prod":
            return
        problems = []
        if self.jwt_secret == "dev-only-change-me":
            problems.append("REGIS_JWT_SECRET must be set in prod")
        if not self.field_key:
            problems.append("REGIS_FIELD_KEY (PAN/CIN encryption) must be set in prod")
        if not self.anthropic_api_key:
            problems.append("REGIS_ANTHROPIC_API_KEY must be set in prod")
        if "sqlite" in self.database_url:
            problems.append("SQLite is not allowed in prod; use Postgres")
        if problems:
            raise RuntimeError("Production config invalid: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
