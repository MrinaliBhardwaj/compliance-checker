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
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def signed_url(self, key: str, expires_s: int = 900) -> str:
        """Time-limited read URL handed to the browser (never a public URL)."""


class LocalStorage(Storage):
    """Filesystem-backed (dev/tests). Root configurable; defaults under the CWD."""

    def __init__(self, root: str | None = None) -> None:
        final_root = (
            str(root) if root is not None else os.getenv("REGIS_LOCAL_STORAGE", ".regis_storage")
        )
        self.root = Path(final_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        # A path comparison, not a string prefix: "<root>_evil" starts with "<root>".
        if not p.is_relative_to(self.root):
            raise ValueError("path traversal blocked")
        return p

    def put(self, key: str, content: bytes, content_type: str | None = None) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return f"file://{key}"

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def signed_url(self, key: str, expires_s: int = 900) -> str:
        # dev: a route can stream the bytes; no real signing locally
        return f"/documents/raw/{key}"


class S3Storage(Storage):
    """S3 in ap-south-1 with KMS server-side encryption in prod; any S3-compatible
    endpoint (MinIO in compose) when REGIS_S3_ENDPOINT_URL is set."""

    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        self._s = get_settings()
        self._endpoint = self._s.s3_endpoint_url
        kwargs: dict = {"region_name": self._s.aws_region}
        if self._endpoint:
            kwargs.update(
                endpoint_url=self._endpoint,
                aws_access_key_id=self._s.s3_access_key,
                aws_secret_access_key=self._s.s3_secret_key,
                config=Config(s3={"addressing_style": "path"}),  # MinIO-style URLs
            )
        self._client = boto3.client("s3", **kwargs)
        self._bucket = self._s.s3_bucket
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        # Dev endpoints start empty; real AWS buckets are provisioned (never created here).
        if self._bucket_ready or not self._endpoint:
            return
        from botocore.exceptions import ClientError

        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)
        self._bucket_ready = True

    def put(self, key: str, content: bytes, content_type: str | None = None) -> str:
        self._ensure_bucket()
        extra = {} if self._endpoint else {"ServerSideEncryption": "aws:kms"}  # no KMS on MinIO
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType=content_type or "application/octet-stream",
            **extra,
        )
        return f"s3://{self._bucket}/{key}"

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def signed_url(self, key: str, expires_s: int = 900) -> str:
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=expires_s
        )


_storage: Storage | None = None


def get_storage() -> Storage:
    """Factory: S3 in prod or whenever an S3 endpoint is configured; local otherwise.
    Cached per process."""
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3Storage() if s.env == "prod" or s.s3_endpoint_url else LocalStorage()
    return _storage
