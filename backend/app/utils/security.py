"""
AutoJob AI — Security Utilities
Password hashing, JWT tokens, and credential encryption.
"""

from datetime import datetime, timedelta, timezone
import base64
import hashlib

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ── Password Hashing ──────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT Tokens ─────────────────────────────────────────

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT token. Returns payload or None if invalid."""
    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None

# ── Credential Encryption ───────────────────────────────

def _get_fernet() -> Fernet:
    """Helper to get a Fernet instance using the configured encryption key."""
    # Ensure key is 32 URL-safe base64-encoded bytes by hashing the settings key
    raw_key = settings.encryption_key.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw_key).digest())
    return Fernet(key)

def encrypt_credential(credential: str) -> str:
    """Encrypt a sensitive credential before storing it in the database."""
    if not credential:
        return ""
    f = _get_fernet()
    return f.encrypt(credential.encode("utf-8")).decode("utf-8")

def decrypt_credential(encrypted_credential: str) -> str:
    """Decrypt a sensitive credential retrieved from the database."""
    if not encrypted_credential:
        return ""
    f = _get_fernet()
    try:
        return f.decrypt(encrypted_credential.encode("utf-8")).decode("utf-8")
    except Exception:
        # If decryption fails (e.g., key rotated or corrupted data), return as is or empty.
        # Returning empty is safer.
        return ""

