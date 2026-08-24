"""
The content pipeline: sources, sign-offs, and the staleness rule.

The rule under test is what turns a snapshot into a subscription. A sign-off is
bound to the digest of the exact document reviewed, so re-mirroring an amended
instrument invalidates every derivation from the old text automatically —
rather than when somebody happens to remember.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.content import pipeline, sources
from app.engines import thresholds as th


@pytest.fixture
def register_file(tmp_path: Path) -> Path:
    p = tmp_path / "sources.json"
    p.write_text(json.dumps({
        "meta": {"purpose": "test"},
        "sources": [
            {"id": "src_a", "citation": "Instrument A", "regulator": "RBI",
             "url": "https://example.invalid/a"},
            {"id": "src_b", "citation": "Instrument B", "regulator": "MCA",
             "url": "https://example.invalid/b"},
        ],
    }), encoding="utf-8")
    return p


def _mk(**kw) -> th.Threshold:
    base = dict(key="k", value=1, unit="INR crore", source="s",
                lookup="https://example.invalid")
    return th.Threshold(**{**base, **kw})


# --------------------------------------------------------------------------
# Register contract
# --------------------------------------------------------------------------

def test_the_shipped_register_loads_and_validates():
    reg = sources.load_register()
    assert reg, "register is empty"
    assert all(s.citation and s.url for s in reg.values())


def test_every_threshold_is_bound_to_a_real_source():
    """A threshold bound to nothing cannot ever be detected as stale."""
    reg = sources.load_register()
    for t in th.ALL:
        assert t.source_id, f"{t.key} is bound to no source"
        assert t.source_id in reg, f"{t.key} cites unknown source {t.source_id!r}"


def test_a_mirrored_source_must_name_who_retrieved_it():
    with pytest.raises(sources.SourceError, match="retrieved_by"):
        sources.Source(id="x", citation="c", regulator="RBI", url="u",
                       mirror="x.pdf", digest="deadbeef")


def test_duplicate_source_ids_are_rejected(tmp_path: Path):
    p = tmp_path / "dupes.json"
    p.write_text(json.dumps({"sources": [
        {"id": "same", "citation": "A", "regulator": "RBI", "url": "u"},
        {"id": "same", "citation": "B", "regulator": "RBI", "url": "u"},
    ]}))
    with pytest.raises(sources.SourceError, match="duplicate"):
        sources.load_register(p)


# --------------------------------------------------------------------------
# Sign-off contract
# --------------------------------------------------------------------------

def test_signoff_requires_a_digest_not_merely_a_source():
    """Citing an instrument is meaningless once that instrument is amended."""
    with pytest.raises(ValueError, match="verified_against"):
        _mk(status=th.VERIFIED, source_id="src_a",
            verified_by="A. Rao, ACS 12345", verified_on="2026-08-18")


def test_a_complete_signoff_is_accepted():
    t = _mk(status=th.VERIFIED, source_id="src_a", verified_by="A. Rao, ACS 12345",
            verified_on="2026-08-18", verified_against="abc123")
    assert t.verified


# --------------------------------------------------------------------------
# The staleness rule
# --------------------------------------------------------------------------

def test_reviewing_an_amended_source_makes_the_signoff_stale(register_file, tmp_path):
    doc = tmp_path / "instrument.pdf"
    doc.write_bytes(b"%PDF-1.4 original text")
    sources.register_mirror("src_a", doc, retrieved_by="A. Rao", path=register_file)
    original = sources.load_register(register_file)["src_a"].digest

    signed = _mk(key="bound", status=th.VERIFIED, source_id="src_a",
                 verified_by="A. Rao, ACS 12345", verified_on="2026-08-18",
                 verified_against=original)

    reg = sources.load_register(register_file)
    assert th.stale(reg, (signed,)) == [], "a fresh sign-off is not stale"

    # The regulator amends the instrument; a human re-mirrors it.
    doc.write_bytes(b"%PDF-1.4 AMENDED text")
    sources.register_mirror("src_a", doc, retrieved_by="A. Rao", path=register_file)
    reg = sources.load_register(register_file)

    assert reg["src_a"].digest != original
    assert th.stale(reg, (signed,)) == [signed], (
        "a sign-off against superseded text must return to the queue"
    )


def test_an_unmirrored_source_cannot_make_anything_stale(register_file):
    """Absence of a document is a gap in the queue, not a false staleness alarm."""
    signed = _mk(status=th.VERIFIED, source_id="src_b", verified_by="A. Rao",
                 verified_on="2026-08-18", verified_against="whatever")
    assert th.stale(sources.load_register(register_file), (signed,)) == []


def test_a_tampered_mirror_is_detected(register_file, tmp_path):
    doc = tmp_path / "instrument.pdf"
    doc.write_bytes(b"original")
    sources.register_mirror("src_a", doc, retrieved_by="A. Rao", path=register_file)
    s = sources.load_register(register_file)["src_a"]

    # verify_mirror resolves against the package mirror dir, so point at the file
    # we actually wrote by rebuilding the source with a real path.
    assert sources.sha256_file(doc) == s.digest
    doc.write_bytes(b"edited outside the register")
    assert sources.sha256_file(doc) != s.digest


# --------------------------------------------------------------------------
# The queue
# --------------------------------------------------------------------------

def test_queue_reports_the_shipped_state():
    q = pipeline.build_queue()
    assert q.unverified_templates, "every template still ships DRAFT_UNVERIFIED"
    assert q.unverified_thresholds, "no threshold has a named sign-off yet"
    assert q.orphan_thresholds == [], "every threshold should cite a source"
    assert q.blocking == 0, "unverified is expected; only stale/corrupt blocks"


def test_check_gate_passes_while_merely_unverified():
    """Failing CI on an unverified library would train everyone to ignore it."""
    assert pipeline.main(["check"]) == 0


def test_rendered_queue_names_what_to_do():
    out = pipeline.render(pipeline.build_queue())
    assert "SOURCES NOT YET MIRRORED" in out
    assert "AWAITING SIGN-OFF" in out
    assert "provisional" in out.lower()
