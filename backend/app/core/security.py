import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Set
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db

JWT_SECRET_KEY = settings.jwt_secret_key
JWT_ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_HOURS = settings.access_token_expire_hours

security_bearer = HTTPBearer(auto_error=False)

# =========================================================================
# RBAC PERMISSIONS CATALOG
# =========================================================================
ROLE_PERMISSIONS = {
    "SUPER_ADMIN": {
        "platform:manage",
        "org:create",
        "org:view_all",
        "org:manage_settings",
        "org:manage_users",
        "users:view_all",
        "users:manage",
        "jobs:view_all",
        "jobs:create_edit",
        "jobs:delete",
        "candidates:view_all",
        "candidates:search_pool",
        "applications:view_all",
        "applications:advance_stage",
        "resumes:upload_analyze",
        "resumes:view_all",
        "interviews:manage",
        "interviews:submit_feedback",
        "plans:manage",
        "ai:view_telemetry",
        "audit:view_all",
        "profile:manage_own"
    },
    "ORG_ADMIN": {
        "org:manage_settings",
        "org:manage_users",
        "jobs:create_edit",
        "jobs:delete",
        "candidates:search_pool",
        "applications:view_tenant",
        "applications:advance_stage",
        "interviews:manage",
        "interviews:submit_feedback",
        "reports:view_analytics",
        "profile:manage_own"
    },
    "EMPLOYER_ADMIN": { # Alias for ORG_ADMIN backward compatibility
        "org:manage_settings",
        "org:manage_users",
        "jobs:create_edit",
        "jobs:delete",
        "candidates:search_pool",
        "applications:view_tenant",
        "applications:advance_stage",
        "interviews:manage",
        "interviews:submit_feedback",
        "reports:view_analytics",
        "profile:manage_own"
    },
    "RECRUITER": {
        "jobs:create_edit",
        "candidates:search_pool",
        "applications:view_tenant",
        "applications:advance_stage",
        "interviews:manage",
        "interviews:submit_feedback",
        "reports:view_analytics",
        "profile:manage_own"
    },
    "HIRING_MANAGER": {
        "jobs:create_edit",
        "candidates:search_pool",
        "applications:view_tenant",
        "interviews:manage",
        "interviews:submit_feedback",
        "reports:view_analytics",
        "profile:manage_own"
    },
    "INTERVIEWER": {
        "interviews:submit_feedback",
        "profile:manage_own"
    },
    "CANDIDATE": {
        "resumes:upload_analyze",
        "applications:apply_own",
        "applications:view_own",
        "profile:manage_own"
    },
    "ANALYST": {
        "reports:view_analytics",
        "jobs:view_all",
        "profile:manage_own"
    }
}

# =========================================================================
# PASSWORD & TOKEN SECURITY
# =========================================================================
PASSWORD_SCHEME = "pbkdf2_sha256"
LEGACY_ITERATIONS = 100_000  # hashes stored as "salt$hash" before iterations were recorded


def _pbkdf2(password: str, salt: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Format: pbkdf2_sha256$<iterations>$<salt>$<hex digest>"""
    salt = salt or secrets.token_hex(16)
    iterations = settings.password_hash_iterations
    return f"{PASSWORD_SCHEME}${iterations}${salt}${_pbkdf2(password, salt, iterations)}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        parts = hashed_password.split("$")
        if len(parts) == 4 and parts[0] == PASSWORD_SCHEME:
            _, iterations, salt, expected = parts
            actual = _pbkdf2(plain_password, salt, int(iterations))
        else:
            salt, expected = parts
            actual = _pbkdf2(plain_password, salt, LEGACY_ITERATIONS)
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def password_needs_rehash(hashed_password: str) -> bool:
    parts = hashed_password.split("$")
    if len(parts) != 4 or parts[0] != PASSWORD_SCHEME:
        return True
    return int(parts[1]) < settings.password_hash_iterations


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

# =========================================================================
# FASTAPI DEPENDENCIES & AUTHORIZATION ENFORCERS
# =========================================================================
def get_current_user_optional(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db)
):
    if not auth or not auth.credentials:
        return None
    payload = decode_access_token(auth.credentials)
    if not payload or "sub" not in payload:
        return None
    
    from app.models.db_models import User
    user = db.query(User).filter(User.id == payload["sub"]).first()
    return user

def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token expired",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not auth or not auth.credentials:
        raise credentials_exception
    payload = decode_access_token(auth.credentials)
    if not payload or "sub" not in payload:
        raise credentials_exception
    
    from app.models.db_models import User
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user

def require_roles(allowed_roles: List[str]):
    def role_checker(current_user = Depends(get_current_user)):
        # Normalize EMPLOYER_ADMIN and ORG_ADMIN
        user_role = current_user.role
        if user_role in allowed_roles:
            return current_user
        if "ORG_ADMIN" in allowed_roles and user_role == "EMPLOYER_ADMIN":
            return current_user
        if "EMPLOYER_ADMIN" in allowed_roles and user_role == "ORG_ADMIN":
            return current_user
            
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Requires one of roles: {', '.join(allowed_roles)}"
        )
    return role_checker

def require_permissions(required_perms: List[str]):
    def permission_checker(current_user = Depends(get_current_user)):
        user_perms = ROLE_PERMISSIONS.get(current_user.role, set())
        for perm in required_perms:
            if perm not in user_perms:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. Missing permission: {perm}"
                )
        return current_user
    return permission_checker

def enforce_tenant_access(current_user, target_org_id: Optional[str]) -> bool:
    """Enforces that a user can only access resources within their own organization unless they are a Super Admin."""
    if not current_user:
        return False
    if current_user.role == "SUPER_ADMIN":
        return True
    if not target_org_id:
        return False
    return current_user.organization_id == target_org_id
