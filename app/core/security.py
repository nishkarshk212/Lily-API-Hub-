"""Cryptographic utilities: password hashing, JWT sessions, AES/Fernet encryption, HMAC."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
import jwt

from app.core.config import Settings, get_settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: Optional[str]) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_api_key_secret(prefix: str = "lily_live_") -> str:
    # 32 bytes -> ~43 URL-safe chars; clear prefix + high entropy.
    return f"{prefix}{secrets.token_urlsafe(32)}"


def generate_random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def mask_secret(value: Optional[str], head: int = 6, tail: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= head + tail:
        return "•" * len(value)
    return f"{value[:head]}••••••••{value[-tail:]}"


def _derive_fernet_key(settings: Settings) -> bytes:
    if settings.ENCRYPTION_KEY and settings.ENCRYPTION_KEY.strip():
        candidate = settings.ENCRYPTION_KEY.strip().encode("utf-8")
        # Validate direct Fernet key; otherwise derive 32-byte key from it.
        try:
            Fernet(candidate)
            return candidate
        except Exception:
            digest = hashlib.sha256(candidate).digest()
            return base64.urlsafe_b64encode(digest)

    # Derive a stable 32-byte key from SECRET_KEY
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        settings.SECRET_KEY.encode("utf-8"),
        b"lily-api-hub-fernet-v1",
        100_000,
        dklen=32,
    )
    return base64.urlsafe_b64encode(dk)


def encrypt_secret(plaintext: str, settings: Optional[Settings] = None) -> str:
    cfg = settings or get_settings()
    fernet = Fernet(_derive_fernet_key(cfg))
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: Optional[str], settings: Optional[Settings] = None) -> Optional[str]:
    if not ciphertext:
        return None
    cfg = settings or get_settings()
    fernet = Fernet(_derive_fernet_key(cfg))
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def create_access_token(
    user_id: str,
    session_id: str,
    role: str,
    expires_hours: Optional[int] = None,
    settings: Optional[Settings] = None,
) -> str:
    cfg = settings or get_settings()
    now = utc_now()
    exp = now + timedelta(hours=expires_hours or cfg.SESSION_EXPIRE_HOURS)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "sid": session_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, cfg.SECRET_KEY, algorithm=cfg.JWT_ALGORITHM)


def decode_access_token(token: str, settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    cfg = settings or get_settings()
    try:
        return jwt.decode(token, cfg.SECRET_KEY, algorithms=[cfg.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def create_signed_state(data: Dict[str, Any], salt: str = "oauth-state", settings: Optional[Settings] = None) -> str:
    cfg = settings or get_settings()
    serializer = URLSafeTimedSerializer(cfg.SECRET_KEY, salt=salt)
    return serializer.dumps(data)


def verify_signed_state(
    token: str,
    salt: str = "oauth-state",
    max_age_seconds: int = 600,
    settings: Optional[Settings] = None,
) -> Optional[Dict[str, Any]]:
    cfg = settings or get_settings()
    serializer = URLSafeTimedSerializer(cfg.SECRET_KEY, salt=salt)
    try:
        return serializer.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None


def verify_hmac_sha256_hex(secret: str, payload: bytes, expected_signature: str) -> bool:
    if not secret or not expected_signature:
        return False
    computed = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected_signature.strip())

