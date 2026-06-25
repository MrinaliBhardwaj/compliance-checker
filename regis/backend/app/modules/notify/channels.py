"""
Delivery channels (email + Slack). Real providers when configured; a Null channel
otherwise so the notification pipeline always records the intent (the Notification
row) even when no provider is wired — delivery is best-effort, the audit trail is not.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import get_settings


class Channel(ABC):
    name: str

    @abstractmethod
    def send(self, *, to: str | None, subject: str, body: str, meta: dict | None = None) -> bool:
        """Return True if actually dispatched to an external provider."""


class NullChannel(Channel):
    """Records only — no external send (dev / no provider configured)."""

    def __init__(self, name: str) -> None:
        self.name = name

    def send(self, *, to: str | None, subject: str, body: str, meta: dict | None = None) -> bool:
        return False


class EmailChannel(Channel):
    name = "email"

    def send(self, *, to: str | None, subject: str, body: str, meta: dict | None = None) -> bool:
        if not to:
            return False
        import boto3
        s = get_settings()
        client = boto3.client("ses", region_name=s.aws_region)
        client.send_email(
            Source=meta.get("from", "compliance@regis.app") if meta else "compliance@regis.app",
            Destination={"ToAddresses": [to]},
            Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}},
        )
        return True


class SlackChannel(Channel):
    name = "slack"

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def send(self, *, to: str | None, subject: str, body: str, meta: dict | None = None) -> bool:
        import httpx
        r = httpx.post(self.webhook_url, json={"text": f"*{subject}*\n{body}"}, timeout=10)
        return r.status_code < 300


def get_channel(channel: str) -> Channel:
    """Pick a real channel when its provider is configured, else Null (still records)."""
    s = get_settings()
    if channel == "email" and s.env == "prod":
        return EmailChannel()
    if channel == "slack":
        webhook = getattr(s, "slack_webhook_url", None)
        if webhook:
            return SlackChannel(webhook)
    return NullChannel(channel)
