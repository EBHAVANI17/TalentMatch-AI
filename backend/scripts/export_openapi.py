"""Write the API's OpenAPI schema to a file (used to generate frontend types).

Usage (from anywhere):  python backend/scripts/export_openapi.py web/openapi.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

target = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
target.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
print(f"Wrote {target} ({len(app.openapi()['paths'])} paths)")
