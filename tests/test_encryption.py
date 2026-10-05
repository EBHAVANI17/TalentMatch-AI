"""Field-level encryption of sensitive columns, and the super-admin endpoints around it."""
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from app.core import crypto
from app.core.database import SessionLocal
from app.db.rotate_encryption import rotate_all
from app.core.security import hash_password
from app.models.db_models import CandidateProfile, User


@pytest.fixture
def keys(monkeypatch):
    """Use explicit DATA_ENCRYPTION_KEYS for one test; restores the cached cipher afterwards."""
    def use(*fernet_keys: bytes):
        monkeypatch.setattr(crypto.settings, "data_encryption_keys", ",".join(k.decode() for k in fernet_keys))
        crypto.reset_cipher()
    yield use
    monkeypatch.undo()
    crypto.reset_cipher()


def _new_profile(db, prefix: str, **fields) -> str:
    profile_id = f"{prefix}_{uuid.uuid4().hex[:8]}"
    db.add(User(id=f"usr_{profile_id}", email=f"{profile_id}@example.com", full_name="Enc Test",
                role="CANDIDATE", hashed_password=hash_password("pw-12345678")))
    db.add(CandidateProfile(id=profile_id, user_id=f"usr_{profile_id}", title="Engineer", **fields))
    db.commit()
    return profile_id


def _raw(table: str, column: str, row_id: str) -> str:
    with SessionLocal() as db:
        return db.execute(text(f"SELECT {column} FROM {table} WHERE id = :id"), {"id": row_id}).scalar()


# ---------------------------------------------------------------- crypto primitives

def test_round_trip_and_prefix():
    token = crypto.encrypt_value("+91 98765 43210")
    assert token.startswith(crypto.ENC_PREFIX) and "98765" not in token
    assert crypto.decrypt_value(token) == "+91 98765 43210"
    assert crypto.encrypt_value(token) == token  # never double-encrypted
    assert crypto.encrypt_value("") == "" and crypto.encrypt_value(None) is None


def test_legacy_plaintext_is_returned_as_is():
    assert crypto.decrypt_value("plain old value") == "plain old value"


def test_tampered_ciphertext_raises():
    token = crypto.encrypt_value("secret")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_value(tampered)


def test_wrong_key_raises(keys):
    keys(Fernet.generate_key())
    token = crypto.encrypt_value("secret")
    keys(Fernet.generate_key())
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_value(token)


def test_key_rotation(keys):
    old, new = Fernet.generate_key(), Fernet.generate_key()
    keys(old)
    token = crypto.encrypt_value("secret")
    keys(new, old)  # new key first, old still listed
    assert crypto.decrypt_value(token) == "secret"
    rotated = crypto.rotate_value(token)
    keys(new)  # old key removed
    assert crypto.decrypt_value(rotated) == "secret"
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_value(token)


def test_dev_key_data_stays_readable_after_configuring_keys(keys):
    token = crypto.encrypt_value("written in development")  # default dev key
    keys(Fernet.generate_key())
    assert crypto.decrypt_value(token) == "written in development"
    assert crypto.decrypt_value(crypto.rotate_value(token)) == "written in development"


def test_status_reports_development_key_truthfully():
    status = crypto.get_encryption_status()
    assert status["status"] == "DEVELOPMENT KEY" and status["key_derived"] is True
    assert status["self_test_passed"] is True
    assert "candidate_profiles.phone" in status["protected_fields"]
    assert not any("API" in f or "Credential" in f for f in status["protected_fields"])


# ---------------------------------------------------------------- database storage

def test_profile_fields_are_ciphertext_in_the_database():
    with SessionLocal() as db:
        profile_id = _new_profile(db, "cand_enc", phone="+1 555 0100",
                                  raw_resume_text="Senior Python engineer, Kubernetes")
    assert _raw("candidate_profiles", "phone", profile_id).startswith(crypto.ENC_PREFIX)
    assert "Kubernetes" not in _raw("candidate_profiles", "raw_resume_text", profile_id)
    with SessionLocal() as db:
        profile = db.get(CandidateProfile, profile_id)
        assert profile.phone == "+1 555 0100"  # the app still sees plaintext
        assert profile.raw_resume_text == "Senior Python engineer, Kubernetes"


def test_rotation_command_encrypts_legacy_plaintext_and_rotates(keys):
    with SessionLocal() as db:
        profile_id = _new_profile(db, "cand_rot")
        # Simulate a row written before encryption existed
        db.execute(text("UPDATE candidate_profiles SET phone = '+44 20 7946 0000' WHERE id = :id"), {"id": profile_id})
        db.commit()
    dev_key, new_key = crypto._derived_dev_key(), Fernet.generate_key()
    try:
        keys(new_key, dev_key)  # rotate the whole (shared) test database to a new key
        with SessionLocal() as db:
            counts = rotate_all(db)
        assert counts["candidate_profiles.phone"] >= 1
        stored = _raw("candidate_profiles", "phone", profile_id)
        assert stored.startswith(crypto.ENC_PREFIX)
        keys(new_key)  # old key removed: everything still readable
        with SessionLocal() as db:
            assert db.get(CandidateProfile, profile_id).phone == "+44 20 7946 0000"
    finally:
        keys(dev_key, new_key)  # rotate back so the rest of the suite runs with the default key
        with SessionLocal() as db:
            rotate_all(db)


# ---------------------------------------------------------------- admin endpoints

def test_encryption_status_and_test_endpoints(client, auth):
    status = client.get("/api/v1/admin/encryption/status", headers=auth("admin"))
    assert status.status_code == 200 and status.json()["self_test_passed"] is True
    ok = client.post("/api/v1/admin/encryption/test", json={"text": "hello"}, headers=auth("admin"))
    assert ok.status_code == 200 and ok.json()["is_valid"] is True
    too_long = client.post("/api/v1/admin/encryption/test", json={"text": "x" * 501}, headers=auth("admin"))
    assert too_long.status_code == 422
    assert client.get("/api/v1/admin/encryption/status", headers=auth("anthropic")).status_code == 403
