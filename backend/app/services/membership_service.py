"""Memberships: who belongs to which organization, with which role.

This module is the only writer of memberships and of the users.organization_id /
users.role mirror columns (the user's *default* organization, kept for the classic
workspace and for tokens issued without an active organization). Access decisions
read memberships through core/tenancy.py, never the mirror.

Rules enforced here:
- Organization roles only (ORG_ROLES); platform accounts (SUPER_ADMIN, CANDIDATE) hold no memberships.
- One-level hierarchy: a client's parent must be org_type=parent; clients can't have clients.
- Parent admins manage a client's memberships only when the client has allow_parent_access.
- An organization always keeps at least one active admin.
- Seats: active memberships + pending invitations must fit the organization's own seat limit.
- Every change is audited in the same transaction as the change itself.
"""
import json
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.db_models import AuditLog, Invitation, Membership, Organization, User, UserToken

# Kept here (not imported from core.tenancy) so tenancy can import this module without a cycle.
ORG_ROLES = {"ORG_ADMIN", "EMPLOYER_ADMIN", "RECRUITER", "HIRING_MANAGER", "INTERVIEWER", "ANALYST"}
ORG_ADMIN_ROLES = {"ORG_ADMIN", "EMPLOYER_ADMIN"}
PLATFORM_ROLES = {"SUPER_ADMIN", "CANDIDATE"}
ACTIVE, SUSPENDED = "active", "suspended"
DELETED_STATUS = "deleted"


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def active_membership(db: Session, user_id: str, org_id: Optional[str]) -> Optional[Membership]:
    if not org_id:
        return None
    return db.query(Membership).filter(
        Membership.user_id == user_id, Membership.organization_id == org_id, Membership.status == ACTIVE
    ).first()


def memberships_for(db: Session, user_id: str) -> List[Membership]:
    return db.query(Membership).filter(Membership.user_id == user_id).order_by(Membership.created_at).all()


def active_members(db: Session, org_id: str) -> List[Membership]:
    return (
        db.query(Membership).join(User, User.id == Membership.user_id)
        .filter(Membership.organization_id == org_id, Membership.status == ACTIVE, User.is_active.is_(True))
        .all()
    )


def seats_in_use(db: Session, org_id: str) -> int:
    members = db.query(Membership).filter(Membership.organization_id == org_id, Membership.status == ACTIVE).count()
    pending = db.query(Invitation).filter(
        Invitation.organization_id == org_id,
        Invitation.status == "pending",
        Invitation.expires_at > datetime.utcnow(),
    ).count()
    return members + pending


def is_org_usable(org: Optional[Organization]) -> bool:
    return org is not None and bool(org.is_active) and org.status != DELETED_STATUS


# ---------------------------------------------------------------------------
# Audit (same transaction as the change)
# ---------------------------------------------------------------------------
def _audit(db: Session, actor: Optional[User], action: str, membership: Membership, **details) -> None:
    db.add(AuditLog(
        id=f"audit_{uuid.uuid4().hex[:10]}",
        organization_id=membership.organization_id,
        user_id=actor.id if actor else None,
        user_email=actor.email if actor else "system",
        action=action,
        module="Memberships",
        entity="Membership",
        entity_id=membership.id,
        details_json=json.dumps({"member_user_id": membership.user_id, "role": membership.role,
                                 "status": membership.status, **details}),
        ip_address="",
    ))


# ---------------------------------------------------------------------------
# Default organization (the mirror columns)
# ---------------------------------------------------------------------------
def sync_default(db: Session, user: User) -> None:
    """Point users.organization_id/role at a valid active membership: keep the current default
    if it's still active, otherwise use the oldest active membership; clear it if there is none."""
    if user.role in PLATFORM_ROLES:
        return
    db.flush()  # sessions don't autoflush; the query below must see pending changes
    actives = (
        db.query(Membership).join(Organization, Organization.id == Membership.organization_id)
        .filter(Membership.user_id == user.id, Membership.status == ACTIVE, Organization.status != DELETED_STATUS)
        .order_by(Membership.created_at, Membership.id)
        .all()
    )
    current = next((m for m in actives if m.organization_id == user.organization_id), None)
    chosen = current or (actives[0] if actives else None)
    user.organization_id = chosen.organization_id if chosen else None
    if chosen:
        user.role = chosen.role


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
def _require_org_role(role: str) -> None:
    if role not in ORG_ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"role must be one of: {', '.join(sorted(ORG_ROLES))}")


def _guard_last_admin(db: Session, membership: Membership, *, new_role: Optional[str] = None,
                      new_status: Optional[str] = None, removing: bool = False) -> None:
    """Refuse a change that would leave the organization without an active admin."""
    was_admin = membership.role in ORG_ADMIN_ROLES and membership.status == ACTIVE
    stays_admin = (not removing
                   and (new_role or membership.role) in ORG_ADMIN_ROLES
                   and (new_status or membership.status) == ACTIVE)
    if not was_admin or stays_admin:
        return
    other_admins = db.query(Membership).filter(
        Membership.organization_id == membership.organization_id,
        Membership.id != membership.id,
        Membership.status == ACTIVE,
        Membership.role.in_(ORG_ADMIN_ROLES),
    ).count()
    if other_admins == 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This is the organization's last active admin. Make another member an admin first.",
        )


def validate_parent(parent: Organization) -> None:
    """One-level hierarchy: only a parent organization can have clients."""
    if parent.org_type != "parent":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Only a parent organization can have client organizations. Clients can't have clients.")
    if not is_org_usable(parent):
        raise HTTPException(status.HTTP_409_CONFLICT, "The parent organization is not active")


def _check_seats(db: Session, org: Organization) -> None:
    if seats_in_use(db, org.id) >= (org.max_recruiter_seats or 0):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Seat limit reached ({org.max_recruiter_seats}). Upgrade the plan or remove a member.",
        )


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def add_member(db: Session, *, org: Organization, user: User, role: str, actor: Optional[User],
               via_parent: bool = False, check_seats: bool = True, make_default: bool = False) -> Membership:
    """Adds (or reactivates) a membership. Caller commits."""
    _require_org_role(role)
    if user.role in PLATFORM_ROLES:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Platform admin and candidate accounts can't join an organization")
    if not is_org_usable(org):
        raise HTTPException(status.HTTP_409_CONFLICT, "Organization is not active")
    existing = db.query(Membership).filter(Membership.user_id == user.id, Membership.organization_id == org.id).first()
    if existing and existing.status == ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "This person is already a member of the organization")
    if check_seats:
        _check_seats(db, org)
    if existing:
        existing.status, existing.role = ACTIVE, role
        membership = existing
        action = "MEMBERSHIP_REACTIVATED"
    else:
        membership = Membership(id=f"mem_{uuid.uuid4().hex[:16]}", user_id=user.id, organization_id=org.id,
                                role=role, status=ACTIVE)
        db.add(membership)
        action = "MEMBERSHIP_CREATED"
    db.flush()
    if make_default or not user.organization_id:
        user.organization_id = org.id
    sync_default(db, user)
    _audit(db, actor, action, membership, via_parent=via_parent, self_added=bool(actor and actor.id == user.id))
    return membership


def create_org_user(db: Session, *, org: Organization, role: str, actor: Optional[User] = None,
                    check_seats: bool = True, **user_fields) -> User:
    """A new staff account whose first membership is in `org` (sign-up, accepted invitation)."""
    _require_org_role(role)
    user = User(id=f"usr_{uuid.uuid4().hex[:10]}", role=role, organization_id=org.id, **user_fields)
    db.add(user)
    db.flush()
    add_member(db, org=org, user=user, role=role, actor=actor or user, check_seats=check_seats, make_default=True)
    return user


def change_role(db: Session, membership: Membership, role: str, actor: Optional[User], via_parent: bool = False) -> Membership:
    _require_org_role(role)
    if role == membership.role:
        return membership
    _guard_last_admin(db, membership, new_role=role)
    previous = membership.role
    membership.role = role
    db.flush()
    sync_default(db, membership.user)
    _audit(db, actor, "MEMBERSHIP_ROLE_CHANGED", membership, previous_role=previous, via_parent=via_parent)
    return membership


def set_status(db: Session, membership: Membership, new_status: str, actor: Optional[User], via_parent: bool = False) -> Membership:
    if new_status not in (ACTIVE, SUSPENDED):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "status must be 'active' or 'suspended'")
    if new_status == membership.status:
        return membership
    _guard_last_admin(db, membership, new_status=new_status)
    if new_status == ACTIVE:
        org = db.get(Organization, membership.organization_id)
        _check_seats(db, org)
    membership.status = new_status
    db.flush()
    if new_status == SUSPENDED:
        _revoke_org_sessions(db, membership.user_id, membership.organization_id)
    sync_default(db, membership.user)
    _audit(db, actor, "MEMBERSHIP_SUSPENDED" if new_status == SUSPENDED else "MEMBERSHIP_REACTIVATED",
           membership, via_parent=via_parent)
    return membership


def remove(db: Session, membership: Membership, actor: Optional[User], via_parent: bool = False) -> None:
    _guard_last_admin(db, membership, removing=True)
    user = membership.user
    _audit(db, actor, "MEMBERSHIP_REMOVED", membership, via_parent=via_parent,
           self_removed=bool(actor and actor.id == membership.user_id))
    _revoke_org_sessions(db, membership.user_id, membership.organization_id)
    db.delete(membership)
    db.flush()
    db.expire(user, ["memberships"])
    sync_default(db, user)


def _revoke_org_sessions(db: Session, user_id: str, org_id: str) -> None:
    """Refresh tokens working in this organization stop working (access tokens fail the membership check)."""
    db.query(UserToken).filter(
        UserToken.user_id == user_id, UserToken.purpose == "refresh",
        UserToken.organization_id == org_id, UserToken.used_at.is_(None),
    ).update({UserToken.used_at: datetime.utcnow()}, synchronize_session=False)


def set_staff_role(db: Session, user: User, org: Organization, role: str, actor: Optional[User]) -> Membership:
    """Platform admin tool: give the account `role` in `org` and make it their default organization."""
    _require_org_role(role)
    if user.role in PLATFORM_ROLES:
        user.role = role  # becomes organization staff
    membership = db.query(Membership).filter(Membership.user_id == user.id, Membership.organization_id == org.id).first()
    if membership is None:
        membership = add_member(db, org=org, user=user, role=role, actor=actor, make_default=True)
    else:
        change_role(db, membership, role, actor)
        set_status(db, membership, ACTIVE, actor)
    user.organization_id = org.id
    sync_default(db, user)
    return membership


def assign_platform_role(db: Session, user: User, role: str, actor: Optional[User]) -> None:
    """Turn an account into SUPER_ADMIN or CANDIDATE: it leaves every organization (last-admin rule applies)."""
    for membership in list(memberships_for(db, user.id)):
        remove(db, membership, actor)
    user.role = role
    user.organization_id = None


# ---------------------------------------------------------------------------
# Organizations in a hierarchy
# ---------------------------------------------------------------------------
def create_client_org(db: Session, *, parent: Organization, actor: User, **fields) -> Organization:
    validate_parent(parent)
    org = Organization(
        id=f"org_{uuid.uuid4().hex[:8]}", org_type="client", parent_id=parent.id, allow_parent_access=True,
        status="Active", is_active=True, **fields,
    )
    db.add(org)
    db.flush()
    db.add(AuditLog(
        id=f"audit_{uuid.uuid4().hex[:10]}", organization_id=org.id, user_id=actor.id, user_email=actor.email,
        action="CLIENT_ORGANIZATION_CREATED", module="Organizations", entity="Organization", entity_id=org.id,
        details_json=json.dumps({"parent_id": parent.id, "name": org.name}), ip_address="",
    ))
    return org


def set_org_type(db: Session, org: Organization, org_type: str) -> None:
    """Platform admins switch standalone <-> parent. Client status comes only from create_client_org."""
    if org_type == org.org_type:
        return
    if org_type not in ("standalone", "parent") or org.org_type == "client":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only standalone and parent organizations can change type")
    if org_type == "standalone" and db.query(Organization).filter(Organization.parent_id == org.id).count():
        raise HTTPException(status.HTTP_409_CONFLICT, "This organization still has client organizations")
    org.org_type = org_type


def soft_delete_org(db: Session, org: Organization) -> None:
    if db.query(Organization).filter(Organization.parent_id == org.id, Organization.status != DELETED_STATUS).count():
        raise HTTPException(status.HTTP_409_CONFLICT, "Delete or move this organization's clients first")
    org.status, org.is_active = DELETED_STATUS, False
    for membership in db.query(Membership).filter(Membership.organization_id == org.id):
        _revoke_org_sessions(db, membership.user_id, org.id)
        if membership.user.organization_id == org.id:
            membership.user.organization_id = None  # recomputed below
            sync_default(db, membership.user)


# ---------------------------------------------------------------------------
# Seed / repair: create memberships for users that only have the mirror columns
# ---------------------------------------------------------------------------
def ensure_memberships_from_mirror(db: Session) -> int:
    created = 0
    users = db.query(User).filter(User.organization_id.isnot(None), User.role.in_(ORG_ROLES)).all()
    for user in users:
        if db.get(Organization, user.organization_id) is None:
            continue
        if db.query(Membership).filter(Membership.user_id == user.id,
                                       Membership.organization_id == user.organization_id).first():
            continue
        db.add(Membership(id=f"mem_{user.id}_{user.organization_id}", user_id=user.id,
                          organization_id=user.organization_id, role=user.role,
                          status=ACTIVE if user.is_active else SUSPENDED))
        created += 1
    db.flush()
    return created
