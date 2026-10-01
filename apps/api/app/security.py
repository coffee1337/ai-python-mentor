"""Small, dependency-light security primitives used by the auth boundary."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerificationError, VerifyMismatchError
except ImportError:  # pragma: no cover - used only in offline test images.
    PasswordHasher = None
    VerificationError = VerifyMismatchError = Exception

_argon2 = PasswordHasher() if PasswordHasher is not None else None


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    if _argon2 is None and os.getenv("APP_ENV", "development").casefold() == "production":
        raise RuntimeError("argon2-cffi is required in production")
    if _argon2 is not None:
        return _argon2.hash(password)
    # Production images install argon2-cffi. This scrypt fallback keeps local,
    # offline tests from ever storing a plain-text password.
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "$scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    if encoded.startswith("$scrypt$"):
        try:
            _, _, n, r, p, salt_text, digest_text = encoded.split("$")
            salt = base64.urlsafe_b64decode(salt_text.encode())
            expected = base64.urlsafe_b64decode(digest_text.encode())
            actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p))
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False
    if _argon2 is None:
        return False
    try:
        return _argon2.verify(encoded, password)
    except (VerificationError, VerifyMismatchError):
        return False


def normalize_email(email: str) -> str:
    return email.strip().casefold()
