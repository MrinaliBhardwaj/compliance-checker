"""
Shared fixtures for the test suite.

The golden profiles below are the EXACT inputs the verified references use. Their
expected outputs are asserted in tests/golden and must never drift silently — that
is the whole point of a compliance regression suite.
"""
from __future__ import annotations

import pytest

from app.seed.library_loader import load_library


@pytest.fixture(scope="session")
def library() -> dict:
    """The live 106-obligation / 29-law seed, structurally validated."""
    return load_library()


@pytest.fixture(scope="session")
def profile_a() -> dict:
    """Profile A — Base-layer small ICC. Golden: 69 / 1 / 39, 22 laws."""
    return {
        "rbi_registered": True, "nbfc_category": "icc", "rbi_layer": "base",
        "deposit_taking": False, "is_listed": False, "has_listed_debt": False,
        "asset_size_cr": 200, "turnover_cr": 30, "employee_count": 35,
        "branch_count": 3, "operating_states": ["MH", "KA"],
        "gst_registered": True, "gst_scheme": "qrmp", "is_isd": False,
        "esi_applicable": True, "has_foreign_investment": False,
        "has_nonresident_payments": False, "has_international_transactions": False,
        "has_reportable_accounts": False, "has_msme_dues": True,
        "csr_applicable": False, "has_sbo": False, "has_capital_changes": False,
        "has_ecb": False, "has_odi": False, "has_eligible_bonus_employees": True,
        "does_digital_lending": True, "has_dlg_arrangements": True,
        "has_floating_rate_retail": True, "is_secured_lender": True,
        "is_large_corporate": False, "has_borrowings": True,
    }


@pytest.fixture(scope="session")
def profile_b() -> dict:
    """Profile B — Middle-layer with listed NCDs, 4 states. Golden: 100 / 1 / 13, 26 laws."""
    return {
        "rbi_registered": True, "nbfc_category": "nd_si", "rbi_layer": "middle",
        "deposit_taking": False, "is_listed": False, "has_listed_debt": True,
        "asset_size_cr": 3000, "turnover_cr": 450, "employee_count": 260,
        "branch_count": 22, "operating_states": ["MH", "KA", "TN", "DL"],
        "gst_registered": True, "gst_scheme": "regular", "is_isd": False,
        "esi_applicable": True, "has_foreign_investment": True,
        "has_nonresident_payments": True, "has_international_transactions": True,
        "has_reportable_accounts": True, "has_msme_dues": True,
        "csr_applicable": True, "has_sbo": True, "has_capital_changes": True,
        "has_ecb": True, "has_odi": False, "has_eligible_bonus_employees": False,
        "does_digital_lending": False, "has_dlg_arrangements": False,
        "has_floating_rate_retail": True, "is_secured_lender": True,
        "is_large_corporate": True, "has_borrowings": True,
    }


@pytest.fixture(scope="session")
def profile_c() -> dict:
    """Profile C — Incomplete profile (soft flags unanswered). Golden: 61 / 27 / 18."""
    return {
        "rbi_registered": True, "nbfc_category": "icc", "rbi_layer": "middle",
        "deposit_taking": False, "is_listed": False, "has_listed_debt": False,
        "asset_size_cr": 520, "turnover_cr": 60, "employee_count": 80,
        "branch_count": 5, "operating_states": ["MH"],
        "gst_registered": True, "gst_scheme": "regular",
        # soft flags intentionally omitted (None)
    }
