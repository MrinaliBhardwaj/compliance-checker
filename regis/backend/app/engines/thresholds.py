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
    source_id: str | None = None     # id in app/content/sources.json
    verified_by: str | None = None   # named CS/CA who signed this off
    verified_on: str | None = None   # ISO date of that sign-off
    verified_against: str | None = None  # sha256 of the exact bytes reviewed
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
        if self.verified:
            missing = [n for n in ("source_id", "verified_by", "verified_on",
                                   "verified_against") if not getattr(self, n)]
            if missing:
                raise ValueError(
                    f"{self.key}: VERIFIED requires {', '.join(missing)}. A sign-off "
                    "names a reviewer, a date, and the digest of the exact document "
                    "reviewed — binding to a source alone is meaningless once that "
                    "document is amended."
                )


# ---------------------------------------------------------------------------
# RBI — Scale Based Regulation
# ---------------------------------------------------------------------------

SBR_MIDDLE_LAYER_ASSET_CR = Threshold(
    key="sbr_middle_layer_asset_cr",
    source_id="rbi_sbr_md_2023",
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
    source_id="rbi_sbr_md_2023",
    value=500,
    unit="INR crore",
    source="RBI Master Direction — Scale Based Regulation for NBFCs, "
           "para 2.7 and its footnote",
    lookup=RBI_MASTER_DIRECTIONS,
    note="LIVE — this is the CRILC / 'notified NBFC' threshold, not a dead "
         "classification. Two distinct things share the Rs.500cr figure and only "
         "one of them died. (1) As an SBR *layer* classification, ND-SI is "
         "superseded: para 2.7 reads references to NBFC-ND-SI as NBFC-ML/UL and "
         "its footnote puts existing ND-SIs of Rs.500cr-Rs.1000cr in the Base "
         "Layer, so the systemic-importance line moved to Rs.1000cr. (2) As the "
         "scope of specific notified obligations, Rs.500cr is retained: CRILC "
         "reporting and weekly SMA/default reporting apply to deposit-taking "
         "NBFCs and non-deposit-taking NBFCs at Rs.500cr and above, independent "
         "of layer — so a Base Layer NBFC between Rs.500cr and Rs.1000cr is in "
         "scope. The Prudential Framework for Resolution of Stressed Assets and a "
         "group-asset aggregation rule reportedly keep the same figure. "
         "rbi_crilc and rbi_crilc_sma_weekly therefore gate on nbfc_category "
         "['nd_si','deposit_taking'], which is the only way this DSL can express "
         "(non-deposit AND >=Rs.500cr) OR deposit-taking — ANDed keys cannot. "
         "sbr_crar and rbi_concentration are genuinely layer-driven and gate on "
         "rbi_layer instead. Reviewer: confirm against primary text, and consider "
         "renaming the emitted value from 'nd_si' to something like "
         "'crilc_notified' so it stops reading as a live SBR classification.",
)

# ---------------------------------------------------------------------------
# Companies Act, 2013
# ---------------------------------------------------------------------------

CSR_TURNOVER_CR = Threshold(
    key="csr_turnover_cr",
    source_id="companies_act_2013_s135",
    value=1000,
    unit="INR crore",
    source="Companies Act, 2013 — s.135(1)",
    lookup=MCA_ACT,
    note="Turnover limb of s.135(1). The section triggers on ANY of three limbs — "
         "turnover, net worth, net profit — so all three are declared here and "
         "derive_csr ORs them. Testing turnover alone made CSR undecidable for "
         "every company below Rs.1000cr turnover, which is most of the "
         "growth-stage segment: a Rs.80cr-turnover NBFC earning over Rs.5cr net "
         "profit is in scope via the profit limb and was being shown as unknown.",
)

CSR_NET_WORTH_CR = Threshold(
    key="csr_net_worth_cr",
    source_id="companies_act_2013_s135",
    value=500,
    unit="INR crore",
    source="Companies Act, 2013 — s.135(1)",
    lookup=MCA_ACT,
    note="Net-worth limb of s.135(1). Independent of the turnover and net-profit "
         "limbs — any one of the three triggers CSR. Shares the Rs.500cr figure "
         "with NDSI_ASSET_CR by coincidence of drafting, not by reference; the "
         "two move independently and must never be collapsed into one constant.",
)

CSR_NET_PROFIT_CR = Threshold(
    key="csr_net_profit_cr",
    source_id="companies_act_2013_s135",
    value=5,
    unit="INR crore",
    source="Companies Act, 2013 — s.135(1)",
    lookup=MCA_ACT,
    note="Net-profit limb of s.135(1). This is the limb that actually catches "
         "profitable growth-stage NBFCs, which is why modelling turnover alone "
         "under-reported CSR for the launch segment. Reviewer: confirm whether "
         "'net profit' here is the s.198 computed figure rather than PAT, and "
         "whether the immediately-preceding-financial-year test applies.",
)

# ---------------------------------------------------------------------------
# GST
# ---------------------------------------------------------------------------

GST_QRMP_TURNOVER_CR = Threshold(
    key="gst_qrmp_turnover_cr",
    source_id="cgst_qrmp",
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
    source_id="esi_act_1948",
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
    CSR_NET_WORTH_CR,
    CSR_NET_PROFIT_CR,
    GST_QRMP_TURNOVER_CR,
    ESI_EMPLOYEE_COUNT,
)

BY_KEY: dict[str, Threshold] = {t.key: t for t in ALL}


def stale(register: dict, thresholds: tuple[Threshold, ...] | None = None) -> list[Threshold]:
    """VERIFIED thresholds whose source has been re-mirrored since sign-off.

    This is what makes content a subscription rather than a snapshot: an amended
    instrument invalidates every derivation from the old text automatically,
    instead of when somebody remembers to look.
    """
    out = []
    for t in (thresholds if thresholds is not None else ALL):
        if not t.verified or not t.source_id:
            continue
        src = register.get(t.source_id)
        if src and src.mirrored and src.digest != t.verified_against:
            out.append(t)
    return out


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
