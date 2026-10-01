"""Start the API on a fresh demo database for end-to-end tests.

Used by web/playwright.config.ts. Every run starts from the seeded demo data.
"""
import os
import sys
import tempfile
from pathlib import Path

port = sys.argv[1] if len(sys.argv) > 1 else "8013"
db_path = Path(tempfile.gettempdir()) / f"talentmatch_e2e_{port}.db"
db_path.unlink(missing_ok=True)

os.environ.update({
    "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
    "DEMO_MODE": "true",
    "ENVIRONMENT": "test",
    "RATE_LIMIT_AUTH": "1000/minute",
    "PASSWORD_HASH_ITERATIONS": "1000",
    "REDIS_URL": "",
})

backend_dir = Path(__file__).resolve().parents[1]
os.chdir(backend_dir)
sys.path.insert(0, str(backend_dir))

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="127.0.0.1", port=int(port), log_level="warning")
