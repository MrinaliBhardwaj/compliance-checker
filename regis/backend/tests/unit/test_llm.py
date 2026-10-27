"""Unit tests — LLM wrapper JSON parsing (no network; `complete` is stubbed)."""

import json

import pytest

from app.ai import llm


def test_complete_json_parses_plain_json(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda *a, **kw: '{"a": 1}')
    assert llm.complete_json("sys", "user") == {"a": 1}


def test_complete_json_strips_code_fence(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda *a, **kw: '```json\n{"a": 1}\n```')
    assert llm.complete_json("sys", "user") == {"a": 1}


def test_complete_json_extracts_object_wrapped_in_prose(monkeypatch):
    # Regression (BUG-02): this fallback path used `re` without importing it.
    monkeypatch.setattr(llm, "complete", lambda *a, **kw: 'Here you go: {"a": 1}')
    assert llm.complete_json("sys", "user") == {"a": 1}


def test_complete_json_raises_when_no_object(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda *a, **kw: "no json here")
    with pytest.raises(json.JSONDecodeError):
        llm.complete_json("sys", "user")
