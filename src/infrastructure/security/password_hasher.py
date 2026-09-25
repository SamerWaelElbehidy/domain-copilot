from __future__ import annotations

import base64
import hashlib
import hmac
import os

from application.ports.security import PasswordHasher

_N, _R, _P, _DKLEN = 2**14, 8, 1, 32


class ScryptPasswordHasher(PasswordHasher):
    """scrypt from the standard library: memory-hard, salted, and stored in
    a self-describing format so parameters can be raised later without
    invalidating existing hashes (OWASP: cryptographic failures)."""

    def hash(self, password: str) -> str:
        salt = os.urandom(16)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
        b64 = base64.b64encode
        return f"scrypt${_N}${_R}${_P}${b64(salt).decode()}${b64(digest).decode()}"

    def verify(self, password: str, stored_hash: str) -> bool:
        try:
            scheme, n, r, p, salt_b64, digest_b64 = stored_hash.split("$")
            if scheme != "scrypt":
                return False
            salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
            actual = hashlib.scrypt(
                password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(actual, expected)
