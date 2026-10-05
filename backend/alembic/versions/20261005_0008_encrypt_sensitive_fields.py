"""encrypt sensitive fields: widen candidate phone, encrypt existing plaintext

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-05 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.crypto import ENC_PREFIX, decrypt_value, encrypt_value


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) pairs stored encrypted by the models
ENCRYPTED_COLUMNS = [
    ("candidate_profiles", "phone"),
    ("candidate_profiles", "raw_resume_text"),
    ("resume_versions", "extracted_text"),
]


def upgrade() -> None:
    # Ciphertext is ~4x longer than the plaintext, so 32 characters no longer fits a phone number.
    with op.batch_alter_table('candidate_profiles') as batch_op:
        batch_op.alter_column('phone', existing_type=sa.String(length=32), type_=sa.String(length=256),
                              existing_nullable=True)

    # Encrypt rows written before encryption existed. Idempotent: encrypted values carry the prefix.
    conn = op.get_bind()
    for table, column in ENCRYPTED_COLUMNS:
        rows = conn.execute(sa.text(
            f"SELECT id, {column} FROM {table} "
            f"WHERE {column} IS NOT NULL AND {column} <> '' AND {column} NOT LIKE :prefix"
        ), {"prefix": ENC_PREFIX + "%"}).fetchall()
        for row_id, value in rows:
            conn.execute(sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id"),
                         {"value": encrypt_value(value), "id": row_id})


def downgrade() -> None:
    # Back to plaintext (needs the same DATA_ENCRYPTION_KEYS), then restore the old width.
    conn = op.get_bind()
    for table, column in ENCRYPTED_COLUMNS:
        rows = conn.execute(sa.text(
            f"SELECT id, {column} FROM {table} WHERE {column} LIKE :prefix"
        ), {"prefix": ENC_PREFIX + "%"}).fetchall()
        for row_id, value in rows:
            conn.execute(sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id"),
                         {"value": decrypt_value(value), "id": row_id})
    with op.batch_alter_table('candidate_profiles') as batch_op:
        batch_op.alter_column('phone', existing_type=sa.String(length=256), type_=sa.String(length=32),
                              existing_nullable=True)
