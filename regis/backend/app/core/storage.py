"""
Evidence storage seam. S3 (ap-south-1, SSE) in production; a local filesystem
adapter for dev/tests so the upload pipeline never depends on a cloud account.

Tenant isolation is baked into the key layout: every object lives under
`<organization_id>/...`, so a signed URL or listing can never cross tenants.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import get_settings


class Storage(ABC):
    @abstractmethod
    def put(self, key: str, content: bytes, content_type: str | None = None) -> str:
        """Store bytes at key; return a stable URL/URI for documents.file_url."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        ...

    @abstractmethod
    def signed_url(self, key: str, expires_s: int = 900) -> str:
        """Time-limited read URL handed to the browser (never a public URL)."""


class LocalStorage(Storage):
    """Filesystem-backed (dev/tests). Root configurable; defaults under the CWD."""

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or os.getenv("REGIS_LOCAL_STORAGE", ".regis_storage")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError("path traversal blocked")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def put(self, key: str, content: bytes, content_type: str | None = None) -> str:
        self._path(key).write_bytes(content)
        return f"file://{key}"

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def signed_url(self, key: str, expires_s: int = 900) -> str:
        # dev: a route can stream the bytes; no real signing locally
        return f"/documents/raw/{key}"


class S3Storage(Storage):
    """Production storage: S3 in ap-south-1 with server-side encryption."""

    def __init__(self) -> None:
        import boto3
        self._s = get_settings()
        self._client = boto3.client("s3", region_name=self._s.aws_region)
        self._bucket = self._s.s3_bucket

    def put(self, key: str, content: bytes, content_type: str | None = None) -> str:
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=content,
            ContentType=content_type or "application/octet-stream",
            ServerSideEncryption="aws:kms",
        )
        return f"s3://{self._bucket}/{key}"

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def signed_url(self, key: str, expires_s: int = 900) -> str:
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=expires_s)


_storage: Storage | None = None


def get_storage() -> Storage:
    """Factory: S3 in prod, local otherwise. Cached per process."""
    global _storage
    if _storage is None:
        _storage = S3Storage() if get_settings().env == "prod" else LocalStorage()
    return _storage
