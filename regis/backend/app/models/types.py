"""
Portable column types.

- `JSONB`: Postgres JSONB in production, plain JSON on SQLite (so integration
  tests can run without Postgres).
- `EncryptedStr`: field-level encryption for identifiers (PAN/CIN/TAN) per the
  PRD security baseline. Uses Fernet when REGIS_FIELD_KEY is set; in dev with no
  key it stores plaintext (and logs once) so local work isn't blocked. Production
  MUST set the key — enforced in app.core.config for non-dev environments.
"""
from __future__ import annotations

import os

from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB
from sqlalchemy.types import TypeDecorator

# JSONB on Postgres, JSON elsewhere.
JSONB = JSON().with_variant(_PG_JSONB, "postgresql")


def _fernet():
    key = os.getenv("REGIS_FIELD_KEY")
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedStr(TypeDecorator):
    """Transparently encrypt/decrypt a string column at the application boundary."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        f = _fernet()
        return f.encrypt(value.encode()).decode() if f else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        f = _fernet()
        if not f:
            return value
        try:
            return f.decrypt(value.encode()).decode()
        except Exception:
            # value predates encryption (dev) — return as-is
            return value
