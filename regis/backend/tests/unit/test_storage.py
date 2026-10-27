"""Unit tests — local storage adapter (dev/test path)."""

import tempfile

import pytest

from app.core.storage import LocalStorage


def test_put_get_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        s = LocalStorage(root=d)
        url = s.put("org1/ent1/doc.pdf", b"hello", "application/pdf")
        assert url == "file://org1/ent1/doc.pdf"
        assert s.get("org1/ent1/doc.pdf") == b"hello"


def test_path_traversal_blocked():
    with tempfile.TemporaryDirectory() as d:
        s = LocalStorage(root=d)
        with pytest.raises(ValueError):
            s.put("../../escape.txt", b"x")


def test_sibling_directory_with_same_prefix_is_blocked():
    """BUG-12: '<root>_evil' starts with '<root>' as a string but is outside it."""
    import os

    with tempfile.TemporaryDirectory() as d:
        s = LocalStorage(root=os.path.join(d, "store"))
        with pytest.raises(ValueError):
            s.put("../store_evil/x.txt", b"x")


class _FakeS3:
    """Records boto3 calls; enough of the client surface for S3Storage."""

    def __init__(self, **kwargs):
        self.kwargs, self.puts, self.created = kwargs, [], []

    def head_bucket(self, Bucket):
        from botocore.exceptions import ClientError

        raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, Bucket):
        self.created.append(Bucket)

    def put_object(self, **kw):
        self.puts.append(kw)


def _s3(monkeypatch, **env):
    """Build the storage the factory would pick under these REGIS_* settings."""
    import boto3

    import app.core.storage as st
    from app.core.config import get_settings

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    made = {}
    monkeypatch.setattr(boto3, "client", lambda svc, **kw: made.setdefault("c", _FakeS3(**kw)))
    monkeypatch.setattr(st, "_storage", None)
    try:
        return st.get_storage(), made
    finally:
        get_settings.cache_clear()


def test_minio_endpoint_selects_s3_without_kms(monkeypatch):
    """BUG-17: an S3 endpoint (MinIO in compose) must be usable outside prod."""
    from app.core.storage import S3Storage

    s, made = _s3(
        monkeypatch,
        REGIS_S3_ENDPOINT_URL="http://minio:9000",
        REGIS_S3_ACCESS_KEY="regis",
        REGIS_S3_SECRET_KEY="regis-secret",
        REGIS_S3_BUCKET="regis-evidence",
    )
    assert isinstance(s, S3Storage)
    assert made["c"].kwargs["endpoint_url"] == "http://minio:9000"
    assert made["c"].kwargs["aws_access_key_id"] == "regis"
    assert s.put("o/e/d/f.pdf", b"x", "application/pdf") == "s3://regis-evidence/o/e/d/f.pdf"
    assert made["c"].created == ["regis-evidence"]  # dev bucket created on first use
    assert "ServerSideEncryption" not in made["c"].puts[0]  # MinIO has no KMS


def test_aws_in_prod_keeps_kms_and_no_endpoint(monkeypatch):
    from app.core.storage import S3Storage

    s, made = _s3(
        monkeypatch,
        REGIS_ENV="prod",
        REGIS_FIELD_KEY="x" * 44,
        REGIS_JWT_SECRET="prod-secret-for-test",
    )
    assert isinstance(s, S3Storage)
    assert made["c"].kwargs.get("endpoint_url") is None
    s.put("k", b"x")
    assert made["c"].puts[0]["ServerSideEncryption"] == "aws:kms"
    assert made["c"].created == []  # prod buckets are provisioned, never auto-created


def test_no_endpoint_outside_prod_is_local(monkeypatch):
    s, _ = _s3(monkeypatch)
    assert isinstance(s, LocalStorage)
