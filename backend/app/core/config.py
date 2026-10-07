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
    # Kept at 24h while the legacy UI (which cannot refresh) is still in use.
    access_token_expire_hours: int = 24
    refresh_token_expire_days: int = 30
    password_min_length: int = 8
    # PBKDF2-SHA256 work factor (OWASP 2023+: 600k). Tests lower it for speed.
    password_hash_iterations: int = 600_000
    # When true, new accounts must confirm their email before they can log in.
    require_email_verification: bool = False
    email_verification_ttl_hours: int = 48
    password_reset_ttl_minutes: int = 60
    invitation_ttl_days: int = 7

    # Field-level encryption for sensitive columns (phone, resume text).
    # Comma-separated Fernet keys, newest first; see app/core/crypto.py for rotation.
    # Empty = a development key derived from JWT_SECRET_KEY (not allowed in production).
    data_encryption_keys: str = ""

    # Public URL of the web app, used in links inside emails
    app_base_url: str = "http://localhost:8000"

    # Email delivery: console (logs only) | ses (Phase 6)
    email_backend: str = "console"
    email_from: str = "Talent Match <no-reply@talentmatch.local>"

    # HTTP
    # Comma-separated list of allowed browser origins
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173"

    # Redis (rate limits now; queues and caching later). Unset = in-memory fallbacks.
    redis_url: str = ""

    # Rate limiting (per client IP). Format: "<count>/<second|minute|hour|day>"
    rate_limit_enabled: bool = True
    rate_limit_default: str = "300/minute"  # any /api/ request
    rate_limit_auth: str = "10/minute"      # login and sign-up
    rate_limit_copilot: str = "20/minute"   # copilot questions (each can make two AI calls)

    # File storage: local (backend/storage/documents) | s3
    storage_backend: str = "local"
    storage_local_dir: str = ""
    max_upload_mb: int = 10
    download_url_ttl_seconds: int = 300
    aws_region: str = ""
    s3_bucket_name: str = ""
    s3_endpoint_url: str = ""  # for S3-compatible stores (MinIO, R2); empty for AWS

    # Embeddings for semantic matching/search.
    #   fastembed: local ONNX model, no API key (downloads ~70 MB on first use)
    #   hashing:   deterministic, offline, keyword-level only (tests / air-gapped installs)
    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Fixed by the database column (pgvector). Changing it needs a migration.
    embedding_dim: int = 384
    embedding_cache_dir: str = ""  # default backend/.cache/fastembed

    # LLM providers (free tiers work). Tried in this order; providers without a key are skipped.
    # With no keys at all, AI features use their deterministic rule-based fallbacks.
    llm_provider_order: str = "groq,gemini,openrouter"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    llm_timeout_seconds: float = 25.0
    llm_cooldown_seconds: int = 60      # skip a provider this long after a rate limit / outage
    # Store model outputs in ai_requests for features whose outputs contain no personal data
    ai_log_outputs: bool = True
    # Per-user cap on AI calls per day (protects free-tier quotas); 0 = unlimited
    ai_user_daily_limit: int = 100

    # Domain events: "inline" delivers right after commit (dev/tests);
    # "worker" leaves delivery to `python -m app.workers.outbox` (production).
    event_dispatch_mode: str = "inline"
    notification_email_enabled: bool = False

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
        if not self.data_encryption_keys.strip():
            problems.append("DATA_ENCRYPTION_KEYS must be set (generate with Fernet.generate_key())")
        if self.demo_mode:
            problems.append("DEMO_MODE must be false")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS must list explicit origins, not '*'")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


settings = Settings()
