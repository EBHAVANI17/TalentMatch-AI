"""Re-encrypt sensitive columns with the newest key in DATA_ENCRYPTION_KEYS.

Run after putting a new key first in DATA_ENCRYPTION_KEYS (old keys still listed):

    python -m app.db.rotate_encryption

Afterwards the old keys can be removed. Also encrypts any legacy plaintext values.
"""
import logging
from typing import Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.crypto import PROTECTED_FIELDS, rotate_value
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def rotate_all(db: Session) -> Dict[str, int]:
    """Returns the number of values rewritten per column. Raw SQL so the ORM types don't decrypt."""
    counts: Dict[str, int] = {}
    for field in PROTECTED_FIELDS:
        table, column = field.split(".")
        rows = db.execute(text(
            f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL AND {column} <> ''"
        )).fetchall()
        for i, (row_id, value) in enumerate(rows, start=1):
            db.execute(text(f"UPDATE {table} SET {column} = :value WHERE id = :id"),
                       {"value": rotate_value(value), "id": row_id})
            if i % BATCH_SIZE == 0:
                db.commit()
        db.commit()
        counts[field] = len(rows)
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        for field, count in rotate_all(db).items():
            logger.info("Re-encrypted %d values in %s", count, field)


if __name__ == "__main__":
    main()
