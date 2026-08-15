"""
Provenance contract for regulatory thresholds.

These tests do not assert that any number is legally correct — no test can do
that. They assert that every number is *traceable*, declared once, and cannot
silently drift from DRAFT_UNVERIFIED to being presented as certain.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.engines import profile_extraction as pe
from app.engines import thresholds as th


def test_every_threshold_names_a_source_and_lookup():
    for t in th.ALL:
        assert t.source.strip(), f"{t.key} has no source instrument"
        assert t.lookup.startswith("https://"), f"{t.key} has no lookup URL"
        assert t.unit.strip(), f"{t.key} has no unit"


def test_registry_keys_are_unique_and_match_attribute_keys():
    keys = [t.key for t in th.ALL]
    assert len(keys) == len(set(keys)), "duplicate threshold key in ALL"
    assert set(th.BY_KEY) == set(keys)


def test_verified_status_requires_a_named_signoff():
    """The invariant that makes VERIFIED mean something."""
    with pytest.raises(ValueError, match="verified_by"):
        th.Threshold(
            key="x", value=1, unit="INR crore", source="s",
            lookup="https://example.invalid", status=th.VERIFIED,
        )


def test_invalid_status_is_rejected():
    with pytest.raises(ValueError, match="invalid status"):
        th.Threshold(
            key="x", value=1, unit="INR crore", source="s",
            lookup="https://example.invalid", status="PROBABLY_FINE",
        )


def test_seed_library_thresholds_are_still_unverified():
    """
    Guards the honesty gate. If this fails because someone verified the
    library, update it deliberately in the same change as the sign-off --
    do not delete it.
    """
    assert len(th.unverified()) == len(th.ALL)
    assert "unverified" in th.worklist().lower()


# ---------------------------------------------------------------------------
# The duplication this module exists to prevent
# ---------------------------------------------------------------------------

_ENGINE_SOURCES = [
    Path(pe.__file__),
    Path(th.__file__).with_name("applicability.py"),
]

# Values that must never reappear as bare literals in engine logic.
_GUARDED = {int(t.value) for t in th.ALL}

# Message idiom in this codebase: "Rs.1000cr". A number baked into user-facing
# text goes stale silently, so it is guarded separately from logic literals.
_RUPEE_IN_TEXT = re.compile(r"Rs\.(\d+)cr")


def _int_literals(source: str) -> list[tuple[int, int]]:
    """(lineno, value) for every integer constant in real code.

    AST rather than text scanning: regex quantifiers like ``\\d{5}`` live
    inside string constants and the ``10`` in ``0.10`` is part of one float,
    so both are correctly invisible here. A line-based pattern flagged all of
    them.
    """
    out = []
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Constant)
                and isinstance(node.value, int)
                and not isinstance(node.value, bool)):
            out.append((node.lineno, node.value))
    return out


def test_no_bare_regulatory_literals_in_engine_logic():
    """
    One legal fact was spread across three sites: derive_rbi_layer, the
    consistency_checks contradiction, and the near-boundary warning band.
    Updating one and missing another would leave the consistency engine
    silently disagreeing with the derivation.
    """
    offenders: list[str] = []
    for path in _ENGINE_SOURCES:
        source = path.read_text()
        lines = source.splitlines()
        for lineno, value in _int_literals(source):
            if value in _GUARDED:
                offenders.append(f"{path.name}:{lineno}: {lines[lineno - 1].strip()}")
    assert not offenders, (
        "regulatory value appears as a bare literal; source it from "
        "thresholds.py so one legal fact stays one number:\n" + "\n".join(offenders)
    )


def test_no_stale_regulatory_values_in_user_facing_messages():
    for path in _ENGINE_SOURCES:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for raw in _RUPEE_IN_TEXT.findall(line):
                assert int(raw) not in _GUARDED, (
                    f"{path.name}:{lineno} hardcodes a regulatory figure in a "
                    f"message: {line.strip()}"
                )


def test_guards_are_not_vacuous():
    """Both guards are worthless if they cannot detect a real offender."""
    assert _GUARDED, "no values guarded"
    assert (1, 1000) in _int_literals("if asset_cr >= 1000: pass\n")
    assert {v for _, v in _int_literals("x = 900 <= a <= 1100\n")} == {900, 1100}
    # the two false positives that defeated the text-scanning version
    assert not _int_literals('p = r"^\\d{5}[A-Z]{2}$"\n')
    assert not [v for _, v in _int_literals("BAND = 0.10\n") if v == 10]
    assert _RUPEE_IN_TEXT.findall('f"near the Rs.1000cr boundary"') == ["1000"]


def test_near_band_is_derived_from_the_threshold():
    assert th.SBR_MIDDLE_LAYER_ASSET_CR.near_band() == (900.0, 1100.0)
    moved = th.Threshold(
        key="k", value=2000, unit="INR crore", source="s",
        lookup="https://example.invalid",
    )
    assert moved.near_band() == (1800.0, 2200.0)


# ---------------------------------------------------------------------------
# Behaviour is unchanged by the refactor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "asset_cr, deposit, expected",
    [
        (None, False, None),
        (999, False, "base"),
        (1000, False, "middle"),
        (5000, False, "middle"),
        (10, True, "middle"),      # deposit-taking is Middle at any size
    ],
)
def test_derive_rbi_layer_boundaries(asset_cr, deposit, expected):
    assert pe.derive_rbi_layer(asset_cr, deposit).value == expected


def _profile(asset_cr):
    """Minimal Field bag for consistency_checks."""
    unknown = pe.Field(None, pe.Source.DEFAULT_UNKNOWN, 0.0)
    return {
        "asset_size_cr": pe.Field(asset_cr, pe.Source.ASKED, 0.97),
        "deposit_taking": pe.Field(False, pe.Source.ASKED, 0.97),
        "branch_count": unknown,
        "operating_states": unknown,
        "has_listed_debt": unknown,
        "is_listed": unknown,
    }


def test_consistency_check_agrees_with_derivation_at_the_boundary():
    """
    The sites that used to hold independent literals must move together: at
    exactly the Middle-Layer figure, deriving 'middle' and calling an asserted
    'base' a contradiction have to be the same decision.
    """
    boundary = int(th.SBR_MIDDLE_LAYER_ASSET_CR.value)
    asserted_base = {"rbi_layer": "base"}

    def contradictions(asset):
        return [i for i in pe.consistency_checks(_profile(asset), asserted_base)
                if i.field == "rbi_layer" and i.severity == "contradiction"]

    assert pe.derive_rbi_layer(boundary, False).value == "middle"
    assert contradictions(boundary), "derivation says Middle but no contradiction raised"

    assert pe.derive_rbi_layer(boundary - 1, False).value == "base"
    assert not contradictions(boundary - 1), "asserted Base below the boundary is valid"


def _cat_issues(asset, deposit, asserted_cat):
    p = _profile(asset)
    p["deposit_taking"] = pe.Field(deposit, pe.Source.ASKED, 0.97)
    return [i for i in pe.consistency_checks(p, {"nbfc_category": asserted_cat})
            if i.field == "nbfc_category"]


def test_understating_category_above_the_threshold_is_a_contradiction():
    """
    The Profile C bug, now caught at runtime: 'icc' at or above Rs.500cr drops
    CRILC scope, which is a missed obligation.
    """
    boundary = int(th.NDSI_ASSET_CR.value)
    issues = _cat_issues(boundary, False, "icc")
    assert [i.severity for i in issues] == ["contradiction"]
    assert "CRILC" in issues[0].detail

    assert _cat_issues(boundary + 500, False, "icc")
    assert not _cat_issues(boundary - 1, False, "icc"), "icc below the threshold is correct"


def test_overstating_category_is_only_a_warning():
    """
    nd_si below Rs.500cr is legitimate -- an NBFC-Factor is notified regardless
    of size, and group-asset aggregation pulls in individually smaller NBFCs.
    Flagging it as a contradiction would be a false positive.
    """
    issues = _cat_issues(int(th.NDSI_ASSET_CR.value) - 1, False, "nd_si")
    assert [i.severity for i in issues] == ["warning"]
    assert "aggregation" in issues[0].detail


def test_category_must_agree_with_the_deposit_taking_flag():
    assert [i.severity for i in _cat_issues(100, True, "icc")] == ["contradiction"]
    assert [i.severity for i in _cat_issues(100, True, "nd_si")] == ["contradiction"]
    assert not _cat_issues(100, True, "deposit_taking")
    assert [i.severity for i in _cat_issues(100, False, "deposit_taking")] == ["contradiction"]


def test_unasserted_category_is_never_flagged():
    """Derived-only profiles must not generate a self-contradiction."""
    assert not _cat_issues(3000, False, None)
    assert not _cat_issues(3000, False, "")


def test_near_boundary_warning_tracks_the_band():
    low, high = th.SBR_MIDDLE_LAYER_ASSET_CR.near_band()
    asserted = {"rbi_layer": "middle"}

    def warnings(asset):
        return [i for i in pe.consistency_checks(_profile(asset), asserted)
                if i.field == "asset_size_cr"]

    assert warnings(low), "lower edge of the band should warn"
    assert warnings(high), "upper edge of the band should warn"
    assert not warnings(low - 1)
    assert not warnings(high + 1)
