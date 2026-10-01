import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.seed import init_db
from app.api.routes import router

settings.validate_for_runtime()
configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply pending migrations, and seed demo data when DEMO_MODE is on
    init_db()
    yield

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Frontier Autonomous Talent & Career Intelligence Network Enterprise API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Request IDs, access logs, security headers, default rate limit
app.add_middleware(RequestContextMiddleware)
# CORS is added last so it wraps everything, including 429 responses
# (origins come from the CORS_ORIGINS env var)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(router, prefix=settings.api_prefix)
# Legacy un-prefixed paths still work, but are hidden from the OpenAPI docs
app.include_router(router, include_in_schema=False)

@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "database": "PostgreSQL" if settings.database_url.startswith("postgres") else "SQLite",
    }

# New React workspace (web/), built to web/dist and served at /app.
# Unknown /app/* paths return index.html so client-side routes (e.g. /app/team) work on reload.
web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
if web_dist.is_dir():
    app.mount("/app/assets", StaticFiles(directory=web_dist / "assets"), name="web-assets")

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    def serve_web_app(path: str = ""):
        candidate = (web_dist / path).resolve()
        if path and candidate.is_file() and web_dist in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(web_dist / "index.html", headers={"Cache-Control": "no-cache"})

# Legacy single-page UI, served at the site root until every screen has moved to /app
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/", include_in_schema=False)
    def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
