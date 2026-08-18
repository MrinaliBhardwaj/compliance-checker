"""
Structured logging + optional error tracking.

Two rules that come out of how this system fails:

1. **Every log line carries tenant context.** The worker walks organisations in a
   loop and the API is multi-tenant; a message without an `organization_id` is
   nearly useless when one customer's calendar misbehaves. `bind()` attaches
   context for the current task/thread so call sites don't have to thread it.
2. **Logging never raises.** A logging failure must not be able to take down the
   nightly sweep it exists to make observable.

JSON on stdout by default (container-friendly); set REGIS_LOG_FORMAT=text for a
readable local console. No new hard dependency — stdlib only. Sentry is wired
lazily and only if REGIS_SENTRY_DSN is set.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time
import uuid
from contextlib import contextmanager
from typing import Any

_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "regis_log_context", default=None)


def _ctx() -> dict[str, Any]:
    return _context.get() or {}

# Attributes the stdlib puts on every record; anything else is caller-supplied
# and belongs in the JSON payload.
_STD = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "asctime", "message", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(_ctx())
        for k, v in record.__dict__.items():
            if k not in _STD and not k.startswith("_"):
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        try:
            return json.dumps(payload, default=str)
        except Exception:  # never let a log line raise
            return json.dumps({"level": record.levelname, "msg": record.getMessage()})


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx = " ".join(f"{k}={v}" for k, v in _ctx().items())
        extra = " ".join(f"{k}={v}" for k, v in record.__dict__.items()
                         if k not in _STD and not k.startswith("_"))
        line = f"{record.levelname:<7} {record.name:<28} {record.getMessage()}"
        for part in (ctx, extra):
            if part:
                line += f"  {part}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(level: str | None = None) -> None:
    """Idempotent root-logger setup. Safe to call from API and worker alike."""
    root = logging.getLogger()
    if getattr(root, "_regis_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        TextFormatter() if os.getenv("REGIS_LOG_FORMAT", "json") == "text"
        else JsonFormatter())
    root.handlers = [handler]
    root.setLevel((level or os.getenv("REGIS_LOG_LEVEL", "INFO")).upper())
    # uvicorn duplicates access logs through its own handlers; route them here.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    root._regis_configured = True  # type: ignore[attr-defined]
    _init_error_tracking()


def _init_error_tracking() -> None:
    """Sentry if a DSN is configured; a no-op (and never fatal) otherwise."""
    dsn = os.getenv("REGIS_SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, environment=os.getenv("REGIS_ENV", "dev"),
                        traces_sample_rate=0.0, send_default_pii=False)
        logging.getLogger(__name__).info("error tracking enabled")
    except Exception:
        logging.getLogger(__name__).warning("sentry init failed; continuing", exc_info=True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


@contextmanager
def bind(**fields: Any):
    """Attach context to every log line emitted inside the block."""
    token = _context.set({**_ctx(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]
