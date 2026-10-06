"""Password hashing for email + password accounts (stdlib scrypt, no extra dependency)."""

import base64
import functools
import hashlib
import hmac
import secrets

# OWASP minimum for scrypt: N=2^17, r=8, p=1 (~128 MiB). Stored per hash so it can be raised later.
_N, _R, _P = 2**17, 8, 1
_MAXMEM = 256 * 1024 * 1024


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, _N, _R, _P)
    b64 = base64.b64encode
    return f"scrypt${_N}${_R}${_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
    except ValueError:
        return False
    return hmac.compare_digest(actual, base64.b64decode(digest))


@functools.cache
def dummy_hash() -> str:
    """Verified against when the email has no password, so timing doesn't reveal which exist."""
    return hash_password(secrets.token_urlsafe(16))
