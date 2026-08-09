"""
Regulatory numeric constants, with provenance.

Every number in this file is a *legal* threshold, not an engineering one. Each
carries the instrument it must be re-derived from, a verification status using
the same vocabulary as the obligation library (DRAFT_UNVERIFIED | VERIFIED), and
the reviewer who signed it off.

Two rules:

1. **A threshold is declared here exactly once.** Before this module the SBR
   Middle-Layer figure existed as a bare `1000` in `derive_rbi_layer` AND again
   in `consistency_checks` — two literals for one legal fact, so updating one
   would have left the consistency engine silently contradicting the derivation.
2. **Never edit `value` without editing `status`, `verified_by`, `verified_on`
   and `source` in the same change.** A number whose provenance still says
   DRAFT_UNVERIFIED is a number no customer should be shown as certain; that is
   the same contract `library_loader` enforces for obligation templates.

Re-derive from the primary instrument on rbi.org.in / the relevant statute —
never from a secondary summary. Law-firm notes and news summaries have already
been observed to conflate the 29 April 2026 Amendment Directions (Type I
registration exemption, CoR surrender) with a Base/Middle/Upper layer revision,
which they are not.
"""
from __future__ import annotations

from dataclasses import dataclass

DRAFT_UNVERIFIED = "DRAFT_UNVERIFIED"
VERIFIED = "VERIFIED"

# Lookup roots for re-derivation. Deliberately index pages, not deep links —
# a fabricated document ID is worse than no link at all.
RBI_MASTER_DIRECTIONS = "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx"
RBI_NBFC_NOTIFICATIONS = "https://www.rbi.org.in/Scripts/BS_ViewNBFCNotification.aspx"
MCA_ACT = "https://www.mca.gov.in/content/mca/global/en/acts-rules/ebooks/acts.html"
GST_PORTAL = "https://www.gst.gov.in/"
ESIC_ACT = "https://www.esic.gov.in/"


@dataclass(frozen=True)
class Threshold:
    """A legal threshold and the evidence trail behind it."""

    key: str
    value: int | float
    unit: str
    source: str                  # exact instrument to re-derive from
    lookup: str                  # where to find that instrument
    status: str = DRAFT_UNVERIFIED
    verified_by: str | None = None   # named CS/CA who signed this off
    verified_on: str | None = None   # ISO date of that sign-off
    note: str = ""

    @property
    def verified(self) -> bool:
        return self.status == VERIFIED

    def near_band(self, pct: float = 0.10) -> tuple[float, float]:
        """
        Inclusive window either side of the threshold, for "you are close to a
        boundary, confirm the exact figure" warnings. Derived rather than
        hand-written so the band moves when the threshold does.
        """
        delta = self.value * pct
        return (self.value - delta, self.value + delta)

    def __post_init__(self) -> None:
        if self.status not in (DRAFT_UNVERIFIED, VERIFIED):
            raise ValueError(f"{self.key}: invalid status {self.status!r}")
        if self.verified and not (self.verified_by and self.verified_on):
            raise ValueError(
                f"{self.key}: VERIFIED requires both verified_by and verified_on"
            )


# ---------------------------------------------------------------------------
# RBI — Scale Based Regulation
# ---------------------------------------------------------------------------

SBR_MIDDLE_LAYER_ASSET_CR = Threshold(
    key="sbr_middle_layer_asset_cr",
    value=1000,
    unit="INR crore",
    source="RBI Master Direction — Scale Based Regulation for NBFCs "
           "(as consolidated in the NBFC Registration, Exemptions and Framework "
           "for Scale Based Regulation Directions, 2025)",
    lookup=RBI_MASTER_DIRECTIONS,
    note="Non-deposit-taking NBFC at/above this asset size sits in the Middle "
         "Layer. Deposit-taking NBFCs are Middle Layer at any size, handled "
         "separately in derive_rbi_layer. NOT changed by the 29 Apr 2026 "
         "Amendment Directions, which govern Type I registration exemption and "
         "CoR surrender rather than layer boundaries — confirm both points.",
)

NDSI_ASSET_CR = Threshold(
    key="ndsi_asset_cr",
    value=500,
    unit="INR crore",
    source="RBI Master Direction — Scale Based Regulation for NBFCs, "
           "para 2.7 and its footnote",
    lookup=RBI_MASTER_DIRECTIONS,
    note="VESTIGIAL as of the 2026-08-08 re-key — no obligation template reads "
         "nbfc_category any more. As a *classification* the ND-SI category is "
         "superseded: SBR para 2.7 reads references to NBFC-ND-SI as NBFC-ML/UL, "
         "and its footnote reclassifies existing ND-SIs of Rs.500cr-Rs.1000cr as "
         "Base Layer, i.e. the systemic-importance line moved to Rs.1000cr. The "
         "four templates that gated on 'nd_si' (rbi_crilc, rbi_crilc_sma_weekly, "
         "sbr_crar, rbi_concentration) now key off rbi_layer ['middle','upper']. "
         "derive_regulatory_category still emits nd_si/icc into the profile, but "
         "nothing downstream consumes it. "
         "KEPT, not deleted, because Rs.500cr appears to survive as a live "
         "threshold in specific retained regulations — the Prudential Framework "
         "for Resolution of Stressed Assets, and a group-asset aggregation rule. "
         "Reviewer: (a) confirm para 2.7 against primary text; (b) decide whether "
         "any obligation should be re-keyed BACK onto a Rs.500cr rule citing the "
         "instrument that retains it — CRILC is the likeliest candidate, since it "
         "is tied to the stressed-assets framework; (c) if nothing is, retire "
         "nbfc_category and this constant together. Secondary sources only — "
         "rbi.org.in unreachable from the authoring sandbox.",
)

# ---------------------------------------------------------------------------
# Companies Act, 2013
# ---------------------------------------------------------------------------

CSR_TURNOVER_CR = Threshold(
    key="csr_turnover_cr",
    value=1000,
    unit="INR crore",
    source="Companies Act, 2013 — s.135(1)",
    lookup=MCA_ACT,
    note="Turnover limb only. s.135 also triggers on net worth (Rs.500cr) and "
         "net profit (Rs.5cr); derive_csr currently tests turnover alone and "
         "returns DEFAULT_UNKNOWN below it, so the other two limbs are unmodelled.",
)

# ---------------------------------------------------------------------------
# GST
# ---------------------------------------------------------------------------

GST_QRMP_TURNOVER_CR = Threshold(
    key="gst_qrmp_turnover_cr",
    value=5,
    unit="INR crore",
    source="CGST Rules — Quarterly Return Monthly Payment scheme eligibility",
    lookup=GST_PORTAL,
    note="Eligibility ceiling, not an automatic classification — QRMP is an "
         "election. derive_gst_scheme already flags this at confidence 0.70.",
)

# ---------------------------------------------------------------------------
# Labour
# ---------------------------------------------------------------------------

ESI_EMPLOYEE_COUNT = Threshold(
    key="esi_employee_count",
    value=10,
    unit="employees",
    source="Employees' State Insurance Act, 1948 — s.2(12), as applied by "
           "state notification",
    lookup=ESIC_ACT,
    note="State-varying: several states notify 20 rather than 10. A single "
         "national constant is a known simplification — the reviewer should "
         "decide whether this becomes a per-state map before launch.",
)


# ---------------------------------------------------------------------------
# Registry + reviewer worklist
# ---------------------------------------------------------------------------

ALL: tuple[Threshold, ...] = (
    SBR_MIDDLE_LAYER_ASSET_CR,
    NDSI_ASSET_CR,
    CSR_TURNOVER_CR,
    GST_QRMP_TURNOVER_CR,
    ESI_EMPLOYEE_COUNT,
)

BY_KEY: dict[str, Threshold] = {t.key: t for t in ALL}


def unverified() -> list[Threshold]:
    """Thresholds still awaiting a named sign-off, for the review queue."""
    return [t for t in ALL if not t.verified]


def worklist() -> str:
    """Reviewer-facing checklist: what to look up, and where."""
    pending = unverified()
    if not pending:
        return "All regulatory thresholds carry a named sign-off."
    lines = [
        f"{len(pending)} of {len(ALL)} regulatory thresholds are unverified.",
        "Re-derive each from the primary instrument — never a summary.",
        "",
    ]
    for t in pending:
        lines += [
            f"[ ] {t.key} = {t.value} {t.unit}",
            f"      source: {t.source}",
            f"      lookup: {t.lookup}",
        ]
        if t.note:
            lines.append(f"      note:   {t.note}")
        lines.append("")
    return "\n".join(lines).rstrip()


if __name__ == "__main__":  # pragma: no cover - operator convenience
    print(worklist())
