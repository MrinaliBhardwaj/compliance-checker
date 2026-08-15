"""
Golden regression — profile extraction (loop closure into applicability).

Locked: clean payload -> 99 applicable downstream; messy payload -> states
normalized, malformed CIN flagged, FDI gap (+3) ranked above intl-txn (+1),
62 applicable / 33 review composition (the messy payload's asset size
parses to Rs.1.5cr -- see test_messy_composition -- so it lands in the Base
Layer and picks up the Base Layer concentration policy).
"""
import pytest

from app.engines.applicability import generate_compliance_universe
from app.engines.profile_extraction import extract_profile, parse_amount_cr

pytestmark = pytest.mark.golden


RAW_CLEAN = {
    "cin": "U65999MH2018PTC123456", "pan": "AAACT1234A",
    "nbfc_type": "Investment and Credit Company",
    "asset_size": "3000", "turnover": "450",
    "deposit_taking": "No", "is_listed": "No", "has_listed_debt": "Yes",
    "operating_states": ["MH", "KA", "TN", "DL"],
    "branch_count": 22, "employee_count": 260, "gst_registered": "Yes",
    "has_foreign_investment": "Yes", "has_ecb": "Yes", "is_secured_lender": "Yes",
    "has_borrowings": "Yes", "is_large_corporate": "Yes", "has_msme_dues": "Yes",
    "has_floating_rate_retail": "Yes", "has_capital_changes": "Yes", "has_sbo": "Yes",
    "has_nonresident_payments": "Yes", "has_international_transactions": "Yes",
    "has_reportable_accounts": "Yes",
}

RAW_MESSY = {
    "cin": "U65999MH", "pan": "AAACT1234A",          # malformed CIN
    "nbfc_type": "microfinance",
    "asset_size": "around 3 thousand crore",          # free text
    "turnover": "₹4,50 Cr",
    "rbi_layer": "Base",                              # contradicts asset size
    "deposit_taking": "No",
    "operating_states": "Maharashtra, Karnataka and Tamil Nadu",  # full names + 'and'
    "branch_count": 12, "employee_count": 40, "gst_registered": "Yes",
}


def test_clean_payload_closes_loop_to_99(library):
    r = extract_profile(RAW_CLEAN, library)
    uni = generate_compliance_universe(library, r["profile"])
    assert uni["summary"]["applicable"] == 99


def test_clean_derivations(library):
    r = extract_profile(RAW_CLEAN, library)
    p = r["profile"]
    assert p["nbfc_category"] == "nd_si"
    assert p["rbi_layer"] == "middle"
    assert p["esi_applicable"] is True
    assert p["gst_scheme"] == "regular"


def test_messy_states_normalized(library):
    r = extract_profile(RAW_MESSY, library)
    assert r["profile"]["operating_states"] == ["KA", "MH", "TN"]


def test_messy_malformed_cin_flagged(library):
    r = extract_profile(RAW_MESSY, library)
    details = [i["detail"] for i in r["issues"]]
    assert any("cin" in d.lower() and "format" in d.lower() for d in details)


def test_messy_gap_ranking_fdi_before_intl(library):
    """Verified ranking: FDI (+3) surfaces ahead of international transactions (+1)."""
    r = extract_profile(RAW_MESSY, library)
    fields = [g["field"] for g in r["gap_questions"]]
    assert "has_foreign_investment" in fields
    assert "has_international_transactions" in fields
    assert fields.index("has_foreign_investment") < fields.index("has_international_transactions")


def test_messy_asset_size_misparses_thousand(library):
    """
    KNOWN ENGINE BUG, pinned so it stays visible.

    parse_amount_cr("around 3 thousand crore") returns 1.5, not 3000. The
    "thousand" -> "000" substitution produces "3 000", which the band branch
    reads as the two-number band [3.0, 0.0] and averages to 1.5.

    Consequence for a real customer: an NBFC that types its asset size as free
    text in that shape is classified Base Layer instead of Middle Layer and
    silently loses its entire Middle/Upper Layer obligation set. That is a
    missed-obligation bug, not a cosmetic one.

    Fixing it moves the messy composition golden from 62 well upward. Delete
    this test in the same change that fixes parse_amount_cr.
    """
    assert parse_amount_cr("around 3 thousand crore").value == 1.5
    r = extract_profile(RAW_MESSY, library)
    assert r["profile"]["rbi_layer"] == "base"      # should be middle at Rs.3000cr
    assert r["profile"]["asset_size_cr"] == 1.5


def test_messy_composition_62_33(library):
    r = extract_profile(RAW_MESSY, library)
    s = generate_compliance_universe(library, r["profile"])["summary"]
    assert s["applicable"] == 62
    assert s["needs_review"] == 33


def test_review_list_is_unknown_union_lowconf(library):
    """review_fields = derived ∪ low-confidence ∪ unknown (provenance contract)."""
    r = extract_profile(RAW_CLEAN, library)
    prov = r["provenance"]
    for f in r["review_fields"]:
        assert prov[f]["source"] == "DEFAULT_UNKNOWN" or prov[f]["confidence"] < 0.85
