import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password, create_access_token,
    get_current_user
)
from app.models.db_models import User, Organization, CandidateProfile
from app.models.schemas import (
    LoginRequest, TokenResponse, RegisterCandidateRequest,
    RegisterEmployerRequest, UserOut
)
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/auth", tags=["Authentication & Access"])

@router.post("/login", response_model=TokenResponse)
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

    token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
    log_audit_event(
        db=db,
        action="USER_LOGIN",
        module="Auth",
        entity="User",
        entity_id=user.id,
        user_id=user.id,
        user_email=user.email,
        details={"role": user.role}
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user)
    )

@router.post("/register/candidate", response_model=TokenResponse)
def register_candidate(payload: RegisterCandidateRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists"
        )

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
        is_active=True
    )
    db.add(user)
    db.flush()

    import json
    profile = CandidateProfile(
        id=cand_profile_id,
        user_id=user_id,
        title=payload.title,
        bio="Frontier software engineer building scalable systems.",
        skills_json=json.dumps(payload.skills),
        experience_years=payload.experience_years,
        location=payload.location,
        remote_preference=payload.remote_preference,
        expected_salary=payload.expected_salary,
        education="Bachelor's in Computer Science",
        ats_score=92,
        profile_strength=95
    )
    db.add(profile)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
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

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user)
    )

@router.post("/register/employer", response_model=TokenResponse)
def register_employer(payload: RegisterEmployerRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists"
        )

    org_id = f"org_{uuid.uuid4().hex[:8]}"
    org = Organization(
        id=org_id,
        name=payload.company_name,
        domain=payload.company_domain,
        industry=payload.industry,
        plan_tier="Enterprise",
        logo_icon="briefcase",
        website=f"https://{payload.company_domain}"
    )
    db.add(org)
    db.flush()

    user_id = f"usr_emp_{uuid.uuid4().hex[:8]}"
    user = User(
        id=user_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role="EMPLOYER_ADMIN",
        organization_id=org_id,
        avatar_url="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
    log_audit_event(
        db=db,
        action="ORGANIZATION_REGISTERED",
        module="Auth",
        entity="Organization",
        entity_id=org_id,
        user_id=user.id,
        user_email=user.email,
        details={"company": payload.company_name}
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user)
    )

@router.get("/me", response_model=UserOut)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
