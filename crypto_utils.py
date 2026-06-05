"""
Symmetric encryption helpers for secrets stored at rest (e.g. Kismet API keys).

Values are encrypted with Fernet (AES-128-CBC + HMAC). The key is taken from
KISMET_DB_ENCRYPTION_KEY if set (a urlsafe-base64 32-byte Fernet key), otherwise
derived from SESSION_SECRET via HKDF. This means possession of the database file
alone is not enough to recover the plaintext - the process environment is also
required.
"""

import os
import base64
import logging

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    _CRYPTO_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when dependency missing
    _CRYPTO_AVAILABLE = False

# Marks a value as ciphertext produced by this module, so legacy plaintext rows
# written before encryption was enabled can be detected and migrated lazily.
_PREFIX = "enc:v1:"

_fernet = None


def _get_fernet():
    """Build (and cache) the Fernet instance from the configured key material."""
    global _fernet
    if _fernet is not None:
        return _fernet

    if not _CRYPTO_AVAILABLE:
        raise RuntimeError(
            "The 'cryptography' package is required to encrypt stored secrets. "
            "Install it with: pip install cryptography"
        )

    explicit = os.environ.get("KISMET_DB_ENCRYPTION_KEY")
    if explicit:
        _fernet = Fernet(explicit.encode() if isinstance(explicit, str) else explicit)
        return _fernet

    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET must be set to derive a database encryption key "
            "(or set KISMET_DB_ENCRYPTION_KEY explicitly)."
        )

    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"kismet-webui::db-secret::v1",
        info=b"push-service-api-keys",
    ).derive(secret.encode("utf-8"))
    _fernet = Fernet(base64.urlsafe_b64encode(derived))
    return _fernet


def encrypt_value(plaintext):
    """Encrypt a string for storage. None/empty pass through unchanged."""
    if plaintext is None:
        return None
    if plaintext == "":
        return ""
    token = _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_value(stored):
    """Decrypt a stored value. Legacy plaintext (no prefix) is returned as-is."""
    if stored is None:
        return None
    if stored == "":
        return ""
    if not stored.startswith(_PREFIX):
        # Written before encryption was enabled; return verbatim so it still works.
        return stored
    token = stored[len(_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except Exception:
        logger.error("Failed to decrypt a stored secret; returning empty string.")
        return ""
