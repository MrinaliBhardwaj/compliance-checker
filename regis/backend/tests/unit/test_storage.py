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
