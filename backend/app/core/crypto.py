"""Field-level encryption for sensitive columns (Fernet: AES-128-CBC + HMAC-SHA256).

Keys come from DATA_ENCRYPTION_KEYS: comma-separated Fernet keys, newest first.
New values are encrypted with the first key; any listed key can decrypt, so keys
can be rotated without downtime:

    1. Generate a key:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    2. Put it first in DATA_ENCRYPTION_KEYS (keep the old ones after it) and restart.
    3. Re-encrypt stored data:  python -m app.db.rotate_encryption
    4. Remove the old keys.

Development without DATA_ENCRYPTION_KEYS uses a key derived from JWT_SECRET_KEY
(production refuses to start that way; see Settings.validate_for_runtime).
Encrypted values are stored as "enc::<token>". Values without the prefix are
treated as legacy plaintext and are encrypted the next time they are saved.
"""
import base64
import hashlib
import logging
from functools import lru_cache
from typing import Any, List, Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy.types import String, Text, TypeDecorator

from app.core.config import settings

logger = logging.getLogger(__name__)

ENC_PREFIX = "enc::"

# Columns protected by EncryptedString / EncryptedText (kept in sync with db_models)
PROTECTED_FIELDS = [
    "candidate_profiles.phone",
    "candidate_profiles.raw_resume_text",
    "resume_versions.extracted_text",
]


class DecryptionError(ValueError):
    """Stored data could not be decrypted with any configured key (wrong or missing key, or tampering)."""


def _derived_dev_key() -> bytes:
    digest = hashlib.sha256(f"talentmatch-dev-data-key:{settings.jwt_secret_key}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _legacy_derived_key() -> bytes:
    """Key used by the first version of this module (sha256 of the JWT secret); decrypt-only."""
    return base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret_key.encode("utf-8")).digest())


def configured_keys() -> List[bytes]:
    return [k.strip().encode() for k in settings.data_encryption_keys.split(",") if k.strip()]


@lru_cache
def get_cipher() -> MultiFernet:
    keys = configured_keys() or [_derived_dev_key()]
    # Decrypt-only fallbacks: data written with the development key or by the first version of
    # this module stays readable after DATA_ENCRYPTION_KEYS is set, until it's rotated.
    for fallback in (_derived_dev_key(), _legacy_derived_key()):
        if fallback not in keys:
            keys.append(fallback)
    return MultiFernet([Fernet(k) for k in keys])


def reset_cipher() -> None:
    """Forget cached keys (tests, or after changing settings at runtime)."""
    get_cipher.cache_clear()


def encrypt_value(plain: Optional[str]) -> Optional[str]:
    if plain is None:
        return None
    text = str(plain)
    if not text or text.startswith(ENC_PREFIX):
        return text
    return ENC_PREFIX + get_cipher().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt_value(stored: Optional[str]) -> Optional[str]:
    if stored is None:
        return None
    text = str(stored)
    if not text.startswith(ENC_PREFIX):
        return text  # legacy plaintext
    try:
        return get_cipher().decrypt(text[len(ENC_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        logger.error("Encrypted value could not be decrypted; check DATA_ENCRYPTION_KEYS")
        raise DecryptionError("Encrypted data could not be decrypted with the configured keys") from exc


def rotate_value(stored: Optional[str]) -> Optional[str]:
    """Re-encrypt with the newest key (and encrypt legacy plaintext)."""
    if stored is None or stored == "":
        return stored
    if not str(stored).startswith(ENC_PREFIX):
        return encrypt_value(stored)
    token = str(stored)[len(ENC_PREFIX):].encode("ascii")
    return ENC_PREFIX + get_cipher().rotate(token).decode("ascii")


def mask_sensitive(val: Optional[str], visible_chars: int = 4) -> str:
    plain = decrypt_value(val) or ""
    if len(plain) <= visible_chars:
        return "*" * len(plain)
    return "*" * (len(plain) - visible_chars) + plain[-visible_chars:]


class EncryptedString(TypeDecorator):
    """A String column whose values are encrypted at rest. Size the column for ciphertext (~4x)."""
    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Optional[str]:
        return encrypt_value(value) if value is not None else None

    def process_result_value(self, value: Any, dialect: Any) -> Optional[str]:
        return decrypt_value(value) if value is not None else None


class EncryptedText(TypeDecorator):
    """A Text column whose values are encrypted at rest."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Optional[str]:
        return encrypt_value(value) if value is not None else None

    def process_result_value(self, value: Any, dialect: Any) -> Optional[str]:
        return decrypt_value(value) if value is not None else None


def get_encryption_status() -> dict:
    """What is actually protected, and how the key is configured."""
    keys = configured_keys()
    try:
        probe = "talentmatch-self-test"
        healthy = decrypt_value(encrypt_value(probe)) == probe
    except Exception:  # pragma: no cover - reported, not raised
        healthy = False
    return {
        "status": ("ACTIVE" if keys else "DEVELOPMENT KEY") if healthy else "ERROR",
        "algorithm": "Fernet (AES-128-CBC + HMAC-SHA256)",
        "key_derived": not keys,
        "key_source": "DATA_ENCRYPTION_KEYS" if keys else "derived from JWT_SECRET_KEY (development only)",
        "keys_configured": len(keys),
        "token_prefix": ENC_PREFIX,
        "protected_fields": PROTECTED_FIELDS,
        "self_test_passed": healthy,
    }
