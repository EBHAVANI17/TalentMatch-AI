"""Account lifecycle: refresh tokens, email verification, password reset, team invitations.

Tokens handed to users are random strings; only their SHA-256 hash is stored.
Every token is single-use and expires.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.adapters.email import EmailMessage, get_email_sender
from app.core.config import settings
from app.core.security import hash_password
from app.models.db_models import Invitation, Organization, User, UserToken

REFRESH = "refresh"
EMAIL_VERIFY = "email_verify"
PASSWORD_RESET = "password_reset"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> Tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, _hash(raw)


def _link(path: str, token: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}{path}?token={token}"


def validate_password(password: str) -> None:
    if len(password) < settings.password_min_length:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Password must be at least {settings.password_min_length} characters",
        )


# ---------------------------------------------------------------------------
# Generic single-use tokens
# ---------------------------------------------------------------------------
def issue_token(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    raw, digest = _new_token()
    db.add(UserToken(
        id=f"tok_{uuid.uuid4().hex[:12]}",
        user_id=user.id,
        purpose=purpose,
        token_hash=digest,
        expires_at=datetime.utcnow() + ttl,
    ))
    db.commit()
    return raw


def consume_token(db: Session, raw: str, purpose: str) -> Optional[User]:
    """Mark a token used and return its user, or None if it is unknown/expired/used."""
    record = db.query(UserToken).filter(UserToken.token_hash == _hash(raw), UserToken.purpose == purpose).first()
    if record is None:
        return None
    if record.used_at is not None:
        if purpose == REFRESH:
            # A refresh token was replayed: assume it leaked and end every session.
            revoke_tokens(db, record.user_id, REFRESH)
        return None
    if record.expires_at < datetime.utcnow():
        return None
    record.used_at = datetime.utcnow()
    db.commit()
    return db.get(User, record.user_id)


def revoke_tokens(db: Session, user_id: str, purpose: str) -> None:
    db.query(UserToken).filter(
        UserToken.user_id == user_id, UserToken.purpose == purpose, UserToken.used_at.is_(None)
    ).update({UserToken.used_at: datetime.utcnow()}, synchronize_session=False)
    db.commit()


# ---------------------------------------------------------------------------
# Refresh tokens (rotating)
# ---------------------------------------------------------------------------
def issue_refresh_token(db: Session, user: User) -> str:
    return issue_token(db, user, REFRESH, timedelta(days=settings.refresh_token_expire_days))


def rotate_refresh_token(db: Session, raw: str) -> Tuple[User, str]:
    user = consume_token(db, raw, REFRESH)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token is invalid or expired")
    return user, issue_refresh_token(db, user)


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------
def send_verification_email(db: Session, user: User) -> None:
    token = issue_token(db, user, EMAIL_VERIFY, timedelta(hours=settings.email_verification_ttl_hours))
    link = _link("/app/verify-email", token)
    get_email_sender().send(EmailMessage(
        to=user.email,
        subject="Confirm your Talent Match email",
        text=f"Hi {user.full_name},\n\nConfirm your email address:\n{link}\n\n"
             f"This link expires in {settings.email_verification_ttl_hours} hours.",
        tags=[EMAIL_VERIFY],
    ))


def verify_email(db: Session, raw: str) -> User:
    user = consume_token(db, raw, EMAIL_VERIFY)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verification link is invalid or expired")
    user.email_verified = True
    db.commit()
    return user


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------
def request_password_reset(db: Session, email: str) -> None:
    """Always succeeds silently so the endpoint can't be used to discover accounts."""
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        return
    revoke_tokens(db, user.id, PASSWORD_RESET)
    token = issue_token(db, user, PASSWORD_RESET, timedelta(minutes=settings.password_reset_ttl_minutes))
    get_email_sender().send(EmailMessage(
        to=user.email,
        subject="Reset your Talent Match password",
        text=f"Hi {user.full_name},\n\nReset your password:\n{_link('/app/reset-password', token)}\n\n"
             f"This link expires in {settings.password_reset_ttl_minutes} minutes. "
             "If you didn't ask for this, you can ignore this email.",
        tags=[PASSWORD_RESET],
    ))


def reset_password(db: Session, raw: str, new_password: str) -> User:
    validate_password(new_password)
    user = consume_token(db, raw, PASSWORD_RESET)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reset link is invalid or expired")
    user.hashed_password = hash_password(new_password)
    user.email_verified = True  # they proved they control the inbox
    db.commit()
    revoke_tokens(db, user.id, REFRESH)  # sign out other sessions
    return user


# ---------------------------------------------------------------------------
# Team invitations
# ---------------------------------------------------------------------------
def seats_in_use(db: Session, org_id: str) -> int:
    members = db.query(User).filter(User.organization_id == org_id, User.is_active.is_(True)).count()
    pending = db.query(Invitation).filter(
        Invitation.organization_id == org_id,
        Invitation.status == "pending",
        Invitation.expires_at > datetime.utcnow(),
    ).count()
    return members + pending


def create_invitation(db: Session, org: Organization, email: str, role: str, invited_by: User) -> Invitation:
    email = email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    if seats_in_use(db, org.id) >= org.max_recruiter_seats:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Seat limit reached ({org.max_recruiter_seats}). Upgrade the plan or remove a member.",
        )
    # Re-inviting replaces any earlier pending invite for the same address.
    db.query(Invitation).filter(
        Invitation.organization_id == org.id, Invitation.email == email, Invitation.status == "pending"
    ).update({Invitation.status: "revoked"}, synchronize_session=False)

    raw, digest = _new_token()
    invitation = Invitation(
        id=f"inv_{uuid.uuid4().hex[:12]}",
        organization_id=org.id,
        email=email,
        role=role,
        token_hash=digest,
        invited_by_user_id=invited_by.id,
        expires_at=datetime.utcnow() + timedelta(days=settings.invitation_ttl_days),
    )
    db.add(invitation)
    db.commit()
    get_email_sender().send(EmailMessage(
        to=email,
        subject=f"{invited_by.full_name} invited you to {org.name} on Talent Match",
        text=f"You've been invited to join {org.name} as {role.replace('_', ' ').title()}.\n\n"
             f"Accept the invitation:\n{_link('/app/accept-invitation', raw)}\n\n"
             f"This invitation expires in {settings.invitation_ttl_days} days.",
        tags=["invitation"],
    ))
    return invitation


def accept_invitation(db: Session, raw: str, full_name: str, password: str) -> User:
    validate_password(password)
    invitation = db.query(Invitation).filter(Invitation.token_hash == _hash(raw)).first()
    if invitation is None or invitation.status != "pending" or invitation.expires_at < datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invitation is invalid or expired")
    if not invitation.organization or not invitation.organization.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization is not active")
    if db.query(User).filter(User.email == invitation.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")

    user = User(
        id=f"usr_{uuid.uuid4().hex[:10]}",
        email=invitation.email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=invitation.role,
        organization_id=invitation.organization_id,
        email_verified=True,  # the invite link was delivered to this address
        is_active=True,
    )
    db.add(user)
    invitation.status = "accepted"
    invitation.accepted_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user
