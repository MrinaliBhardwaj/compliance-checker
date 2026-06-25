"""
Integration — M-team: multi-user Maker-Checker, end to end (SQLite, AI off).

Realistic flow:
  admin invites a preparer + a head -> preparer accepts (sets password) ->
  admin assigns an obligation to the preparer -> preparer starts + submits ->
  head approves (override gate). Plus: last-admin guard, remove-with-reassignment,
  and RBAC (preparer cannot invite / approve).
"""
import os

os.environ.setdefault("REGIS_DATABASE_URL", "sqlite+pysqlite:///:memory:")

from datetime import date  # noqa: E402

import pytest  # noqa: E402

from app.core.security import Principal  # noqa: E402
from app.models.compliance import ObligationInstance  # noqa: E402
from app.modules.obligations import service as obsvc  # noqa: E402
from app.modules.obligations.lifecycle import RolePermissionError  # noqa: E402
from app.modules.onboarding.service import generate_calendar  # noqa: E402
from app.modules.team import service as team  # noqa: E402
from sqlalchemy import select  # noqa: E402

CTX = {
    "window_start": date(2026, 4, 1), "window_end": date(2027, 3, 31),
    "anchors": {"agm_date": date(2026, 9, 25), "tds_return_date": date(2026, 7, 31)},
    "license_expiry": date(2026, 11, 30),
}


def _admin(seeded):
    return Principal(user_id=str(seeded["user_id"]), organization_id=str(seeded["org_id"]),
                     role="compliance_admin")


def test_full_multi_user_maker_checker(db, seeded_org, profile_b):
    org = seeded_org["org_id"]
    admin = _admin(seeded_org)

    # admin invites a preparer and a head
    inv_prep = team.invite_member(db, organization_id=org, email="prep@acme.example",
                                  role="preparer", full_name="Priya Preparer", invited_by=admin.user_id)
    inv_head = team.invite_member(db, organization_id=org, email="head@acme.example",
                                  role="head", full_name="Hari Head", invited_by=admin.user_id)
    assert inv_prep["status"] == "invited" and inv_prep["invite_token"]

    members = team.list_members(db, organization_id=org)
    assert {m["role"] for m in members} == {"compliance_admin", "preparer", "head"}
    assert sum(m["status"] == "invited" for m in members) == 2

    # preparer accepts (new user -> sets password); becomes active
    acc = team.accept_invite(db, token=inv_prep["invite_token"], password="prep-pw-123",
                             full_name="Priya Preparer")
    assert acc["role"] == "preparer"
    prep_user_id = next(m["user_id"] for m in team.list_members(db, organization_id=org)
                        if m["email"] == "prep@acme.example")
    team.accept_invite(db, token=inv_head["invite_token"], password="head-pw-123", full_name="Hari Head")
    head_user_id = next(m["user_id"] for m in team.list_members(db, organization_id=org)
                        if m["email"] == "head@acme.example")

    # generate calendar, then admin assigns a specific instance to the preparer
    generate_calendar(db, organization_id=org, entity_id=seeded_org["entity_id"],
                      profile=profile_b, ctx=CTX)
    inst = db.execute(select(ObligationInstance)
                      .where(ObligationInstance.organization_id == org)).scalars().first()
    obsvc.assign_owner(db, organization_id=org, instance_id=inst.id,
                       owner_user_id=prep_user_id, principal=admin)
    db.refresh(inst)
    assert str(inst.owner_user_id) == str(prep_user_id)

    # preparer (the owner) starts + submits — Maker
    prep = Principal(user_id=str(prep_user_id), organization_id=str(org), role="preparer")
    obsvc.transition(db, organization_id=org, instance_id=inst.id, action="start", principal=prep)
    obsvc.transition(db, organization_id=org, instance_id=inst.id, action="submit", principal=prep)
    db.refresh(inst)
    assert inst.status == "ready_for_review"

    # head approves — Checker (override evidence gate, audited)
    head = Principal(user_id=str(head_user_id), organization_id=str(org), role="head")
    obsvc.transition(db, organization_id=org, instance_id=inst.id, action="approve",
                     principal=head, override_evidence=True, reason="filed via portal")
    db.refresh(inst)
    assert inst.status == "completed" and str(inst.approved_by) == str(head_user_id)


def test_preparer_cannot_act_on_unassigned(db, seeded_org, profile_b):
    org = seeded_org["org_id"]
    generate_calendar(db, organization_id=org, entity_id=seeded_org["entity_id"],
                      profile=profile_b, ctx=CTX)
    inst = db.execute(select(ObligationInstance)
                      .where(ObligationInstance.organization_id == org)).scalars().first()
    stranger = Principal(user_id="00000000-0000-0000-0000-0000000000aa",
                         organization_id=str(org), role="preparer")
    with pytest.raises(RolePermissionError):
        obsvc.transition(db, organization_id=org, instance_id=inst.id, action="start",
                         principal=stranger)


def test_last_admin_cannot_be_demoted_or_removed(db, seeded_org):
    org = seeded_org["org_id"]
    admin_mid = next(m["membership_id"] for m in team.list_members(db, organization_id=org)
                     if m["role"] == "compliance_admin")
    with pytest.raises(team.TeamError):
        team.update_role(db, organization_id=org, membership_id=admin_mid, role="head",
                         actor=seeded_org["user_id"])
    with pytest.raises(team.TeamError):
        team.remove_member(db, organization_id=org, membership_id=admin_mid,
                           reassign_to=None, actor=seeded_org["user_id"])


def test_remove_member_reassigns_obligations(db, seeded_org, profile_b):
    org = seeded_org["org_id"]
    admin = _admin(seeded_org)
    inv = team.invite_member(db, organization_id=org, email="leaver@acme.example",
                             role="preparer", full_name="Leaver", invited_by=admin.user_id)
    team.accept_invite(db, token=inv["invite_token"], password="pw-123456", full_name="Leaver")
    leaver_id = next(m["user_id"] for m in team.list_members(db, organization_id=org)
                     if m["email"] == "leaver@acme.example")

    generate_calendar(db, organization_id=org, entity_id=seeded_org["entity_id"],
                      profile=profile_b, ctx=CTX)
    insts = db.execute(select(ObligationInstance)
                       .where(ObligationInstance.organization_id == org)).scalars().all()
    for i in insts[:3]:
        obsvc.assign_owner(db, organization_id=org, instance_id=i.id,
                           owner_user_id=leaver_id, principal=admin)

    leaver_mid = next(m["membership_id"] for m in team.list_members(db, organization_id=org)
                      if m["email"] == "leaver@acme.example")
    # reassign their work to the admin on removal
    res = team.remove_member(db, organization_id=org, membership_id=leaver_mid,
                             reassign_to=str(seeded_org["user_id"]), actor=admin.user_id)
    assert res["status"] == "removed"
    assert res["reassigned_instances"] == 3
    orphaned = db.execute(
        select(ObligationInstance).where(ObligationInstance.owner_user_id == leaver_id)
    ).scalars().all()
    assert orphaned == []  # nothing left owned by the removed user


def test_duplicate_active_invite_rejected(db, seeded_org):
    org = seeded_org["org_id"]
    inv = team.invite_member(db, organization_id=org, email="dup@acme.example",
                             role="preparer", full_name=None, invited_by=seeded_org["user_id"])
    team.accept_invite(db, token=inv["invite_token"], password="pw-123456", full_name="Dup")
    with pytest.raises(team.TeamError):
        team.invite_member(db, organization_id=org, email="dup@acme.example",
                           role="preparer", full_name=None, invited_by=seeded_org["user_id"])
