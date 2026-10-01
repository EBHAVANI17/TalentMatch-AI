from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(tags=["System"])


class PublicConfig(BaseModel):
    app_name: str
    version: str
    environment: str
    demo_mode: bool
    require_email_verification: bool
    password_min_length: int


@router.get("/config/public", response_model=PublicConfig)
def public_config():
    """Non-secret settings the web clients need before sign-in (e.g. whether to show demo logins)."""
    return PublicConfig(
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        demo_mode=settings.demo_mode,
        require_email_verification=settings.require_email_verification,
        password_min_length=settings.password_min_length,
    )
