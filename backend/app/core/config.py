"""Application settings, loaded from environment variables (and an optional .env file).

Every deploy-specific value lives here. Nothing else in the codebase should read
os.environ directly.
"""
from pathlib import Path
from typing import List

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"


class MatchingWeights(BaseModel):
    skills_weight: float = 0.45
    experience_weight: float = 0.25
    location_weight: float = 0.15
    salary_weight: float = 0.10
    education_weight: float = 0.05


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "TalentMatch AI Enterprise"
    app_version: str = "2.0.0"
    api_prefix: str = "/api/v1"
    environment: str = "development"  # development | test | staging | production
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # Demo personas, 1-click logins and automatic seeding. Must be off in production.
    demo_mode: bool = True

    # Database
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'talentmatch_production.db'}"
    auto_migrate: bool = True  # run Alembic migrations on startup

    # Auth
    jwt_secret_key: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_hours: int = 24

    # HTTP
    # Comma-separated list of allowed browser origins
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173"

    # Redis (rate limits now; queues and caching later). Unset = in-memory fallbacks.
    redis_url: str = ""

    # Rate limiting (per client IP). Format: "<count>/<second|minute|hour|day>"
    rate_limit_enabled: bool = True
    rate_limit_default: str = "300/minute"  # any /api/ request
    rate_limit_auth: str = "10/minute"      # login and sign-up

    # Matching
    weights: MatchingWeights = MatchingWeights()

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "staging"}

    def validate_for_runtime(self) -> None:
        """Refuse to start a production deploy with unsafe defaults."""
        if not self.is_production:
            return
        problems = []
        if self.jwt_secret_key == DEV_JWT_SECRET or len(self.jwt_secret_key) < 32:
            problems.append("JWT_SECRET_KEY must be set to a random value of at least 32 characters")
        if self.demo_mode:
            problems.append("DEMO_MODE must be false")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS must list explicit origins, not '*'")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


settings = Settings()
