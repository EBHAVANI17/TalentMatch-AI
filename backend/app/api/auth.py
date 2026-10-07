import json
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password, password_needs_rehash, create_access_token,
    get_current_user, get_current_user_optional, security_bearer
)
from app.core.tenancy import TenantContext, resolve_context
from app.models.db_models import User, Organization, CandidateProfile, Plan, Membership
from app.models.schemas import (
    LoginRequest, TokenResponse, RegisterCandidateRequest, RegisterEmployerRequest, UserOut,
    RefreshTokenRequest, TokenRequest, ForgotPasswordRequest, ResetPasswordRequest,
    AcceptInvitationRequest, MessageResponse, SwitchOrgRequest
)
from app.services import membership_service
from app.core.config import settings
from app.core.rate_limit import rate_limit
from app.services import account_service
from app.services.audit_service import log_audit_event
from app.events import emit
from app.services.candidate_service import compute_profile_strength
from app.services.skills_service import set_candidate_skills

router = APIRouter(prefix="/auth", tags=["Authentication & Access"])

auth_rate_limit = Depends(rate_limit("auth", lambda: settings.rate_limit_auth))

DEFAULT_SIGNUP_PLAN_ID = "free"


def user_out(db: Session, ctx: TenantContext) -> UserOut:
    """The user as the web apps see it: organization_id and role describe the ACTIVE organization."""
    out = UserOut.model_validate(ctx.user)
    out.organization_id = ctx.org_id
    out.role = ctx.role or out.role
    out.active_organization_id = ctx.org_id
    out.memberships_count = db.query(Membership).filter(
        Membership.user_id == ctx.user.id, Membership.status == membership_service.ACTIVE
    ).count()
    return out


def issue_session(db: Session, user: User, org_id: Optional[str] = None) -> TokenResponse:
    """Access token (JWT) plus a rotating refresh token, both working in one organization.

    org_id must be an active membership; otherwise (or when omitted) the user's default organization is used.
    """
    membership = membership_service.active_membership(db, user.id, org_id) if org_id else None
    if membership is None:
        membership = membership_service.active_membership(db, user.id, user.organization_id)  # membership-guard: ok (default org)
    if membership is not None and not membership_service.is_org_usable(membership.organization):
        membership = None
    ctx = TenantContext(user=user, membership=membership, organization=membership.organization if membership else None)
    claims = {"sub": user.id, "email": user.email, "role": ctx.role}
    if ctx.org_id:
        claims["active_org_id"] = ctx.org_id
    return TokenResponse(
        access_token=create_access_token(data=claims),
        token_type="bearer",
        expires_in=settings.access_token_expire_hours * 3600,
        refresh_token=account_service.issue_refresh_token(db, user, ctx.org_id),
        user=user_out(db, ctx),
    )


def ensure_email_available(db: Session, email: str) -> None:
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists"
        )


@router.post("/login", response_model=TokenResponse, dependencies=[auth_rate_limit])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended or deactivated"
        )
    if settings.require_email_verification and not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please confirm your email address before signing in"
        )

    # Upgrade old password hashes to the current work factor while we have the plaintext.
    if password_needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(payload.password)
    user.last_login_at = datetime.utcnow()
    if user.candidate_profile:
        user.candidate_profile.last_active_at = user.last_login_at
    db.commit()

    log_audit_event(
        db=db,
        action="USER_LOGIN",
        module="Auth",
        entity="User",
        entity_id=user.id,
        user_id=user.id,
        user_email=user.email,
        organization_id=user.organization_id,  # membership-guard: ok (audit label only)
    )
    return issue_session(db, user)


@router.post("/register/candidate", response_model=TokenResponse, dependencies=[auth_rate_limit])
def register_candidate(payload: RegisterCandidateRequest, db: Session = Depends(get_db)):
    ensure_email_available(db, payload.email)
    account_service.validate_password(payload.password)

    user_id = f"usr_cand_{uuid.uuid4().hex[:8]}"
    cand_profile_id = f"cand_{uuid.uuid4().hex[:8]}"

    user = User(
        id=user_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role="CANDIDATE",
        organization_id=None,
        avatar_url="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=200",
        email_verified=False,
        is_active=True
    )
    db.add(user)
    db.flush()

    profile = CandidateProfile(
        id=cand_profile_id,
        user_id=user_id,
        title=payload.title,
        bio="",
        skills_json=json.dumps(payload.skills),
        experience_years=payload.experience_years,
        location=payload.location,
        remote_preference=payload.remote_preference,
        expected_salary=payload.expected_salary,
        education="",
        ats_score=0,  # set when a resume is analysed
        profile_strength=0,
        last_active_at=datetime.utcnow(),
    )
    db.add(profile)
    db.flush()
    set_candidate_skills(db, profile, payload.skills)
    profile.profile_strength = compute_profile_strength(profile)
    emit(db, "candidate.created", actor=user, payload={"candidate_id": cand_profile_id, "source": "self_registered"})
    db.commit()
    db.refresh(user)

    account_service.send_verification_email(db, user)
    log_audit_event(
        db=db,
        action="CANDIDATE_REGISTERED",
        module="Auth",
        entity="CandidateProfile",
        entity_id=cand_profile_id,
        user_id=user.id,
        user_email=user.email,
        details={"title": payload.title}
    )
    return issue_session(db, user)


@router.post("/register/employer", response_model=TokenResponse, dependencies=[auth_rate_limit])
def register_employer(payload: RegisterEmployerRequest, db: Session = Depends(get_db)):
    ensure_email_available(db, payload.email)
    account_service.validate_password(payload.password)
    if db.query(Organization).filter(Organization.domain == payload.company_domain).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An organization with this domain already exists. Ask its admin for an invitation."
        )

    # Self-serve organizations start on the free plan; upgrades go through billing.
    plan = db.get(Plan, DEFAULT_SIGNUP_PLAN_ID)
    org_id = f"org_{uuid.uuid4().hex[:8]}"
    org = Organization(
        id=org_id,
        name=payload.company_name,
        domain=payload.company_domain,
        industry=payload.industry,
        plan_tier=plan.name if plan else "Free",
        max_recruiter_seats=plan.max_recruiter_seats if plan else 1,
        max_active_jobs=plan.max_active_jobs if plan else 2,
        monthly_ai_credits=plan.monthly_ai_credits if plan else 200,
        max_client_orgs=plan.max_client_orgs if plan and plan.max_client_orgs is not None else 10,
        logo_icon="briefcase",
        website=f"https://{payload.company_domain}"
    )
    db.add(org)
    db.flush()

    user = membership_service.create_org_user(
        db, org=org, role="EMPLOYER_ADMIN", check_seats=False,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        avatar_url="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200",
        email_verified=False,
        is_active=True,
    )
    db.commit()
    db.refresh(user)

    account_service.send_verification_email(db, user)
    log_audit_event(
        db=db,
        action="ORGANIZATION_REGISTERED",
        module="Auth",
        entity="Organization",
        entity_id=org_id,
        user_id=user.id,
        user_email=user.email,
        organization_id=org_id,
        details={"company": payload.company_name, "plan": org.plan_tier}
    )
    return issue_session(db, user)


@router.post("/refresh", response_model=TokenResponse, dependencies=[auth_rate_limit])
def refresh_session(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Swap a refresh token for a new access token. Refresh tokens are single-use."""
    user, org_id = account_service.rotate_refresh_token(db, payload.refresh_token)
    return issue_session(db, user, org_id)  # stays in the same organization while it's still a member


@router.post("/logout", response_model=MessageResponse)
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ends every session for the user by revoking their refresh tokens."""
    account_service.revoke_tokens(db, current_user.id, account_service.REFRESH)
    return MessageResponse(message="Signed out")


@router.post("/verify-email", response_model=UserOut)
def verify_email(payload: TokenRequest, db: Session = Depends(get_db)):
    return UserOut.model_validate(account_service.verify_email(db, payload.token))


@router.post("/resend-verification", response_model=MessageResponse, dependencies=[auth_rate_limit])
def resend_verification(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.email_verified:
        return MessageResponse(message="Email is already verified")
    account_service.send_verification_email(db, current_user)
    return MessageResponse(message="Verification email sent")


@router.post("/forgot-password", response_model=MessageResponse, dependencies=[auth_rate_limit])
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    account_service.request_password_reset(db, payload.email)
    return MessageResponse(message="If an account exists for that email, a reset link has been sent")


@router.post("/reset-password", response_model=MessageResponse, dependencies=[auth_rate_limit])
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = account_service.reset_password(db, payload.token, payload.new_password)
    log_audit_event(
        db=db, action="PASSWORD_RESET", module="Auth", entity="User", entity_id=user.id,
        user_id=user.id, user_email=user.email,
    )
    return MessageResponse(message="Password updated. Please sign in again.")


@router.post("/accept-invitation", response_model=TokenResponse, dependencies=[auth_rate_limit])
def accept_invitation(
    payload: AcceptInvitationRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """New people choose a name and password. People who already have an account accept while
    signed in as the invited (verified) email; the invitation adds a membership."""
    if account_service.invited_account_exists(db, payload.token):
        if current_user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in as the invited email to accept this invitation")
        membership = account_service.accept_invitation_as(db, payload.token, current_user)
        user, org_id = current_user, membership.organization_id
    else:
        if not payload.full_name or not payload.password:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "full_name and password are required")
        user = account_service.accept_invitation(db, payload.token, payload.full_name, payload.password)
        org_id = user.organization_id  # membership-guard: ok (the membership just created)
    log_audit_event(
        db=db, action="INVITATION_ACCEPTED", module="Auth", entity="User", entity_id=user.id,
        user_id=user.id, user_email=user.email, organization_id=org_id,
    )
    return issue_session(db, user, org_id)


@router.post("/switch-org", response_model=TokenResponse, dependencies=[auth_rate_limit])
def switch_org(payload: SwitchOrgRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """New token pair working in another organization the caller belongs to."""
    membership = membership_service.active_membership(db, current_user.id, payload.organization_id)
    if membership is None or not membership_service.is_org_usable(membership.organization):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to that organization")
    log_audit_event(
        db=db, action="ORGANIZATION_SWITCHED", module="Auth", entity="Organization", entity_id=membership.organization_id,
        user_id=current_user.id, user_email=current_user.email, organization_id=membership.organization_id,
        details={"role": membership.role},
    )
    return issue_session(db, current_user, membership.organization_id)


@router.get("/me", response_model=UserOut)
def get_current_user_profile(
    db: Session = Depends(get_db),
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
):
    ctx = resolve_context(db, auth.credentials if auth else None)
    if ctx is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Could not validate credentials or token expired",
                            headers={"WWW-Authenticate": "Bearer"})
    return user_out(db, ctx)
