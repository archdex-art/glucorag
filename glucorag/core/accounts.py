"""Account primitives: password hashing, session tokens and login throttling.

Passwords use stdlib scrypt (memory-hard) with a per-password random salt; the encoded
form carries its parameters so they can be raised later without invalidating old hashes.
Session tokens are random bearer secrets; only their SHA-256 is stored, so a leaked
database cannot be replayed as live sessions.
"""

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass, field

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
_DKLEN = 32
MIN_PASSWORD = 10
MAX_PASSWORD = 256


class WeakPasswordError(ValueError):
    pass


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise WeakPasswordError(f"Use at least {MIN_PASSWORD} characters.")
    if len(password) > MAX_PASSWORD:
        raise WeakPasswordError(f"Use at most {MAX_PASSWORD} characters.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=_DKLEN
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = encoded.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
            dklen=len(bytes.fromhex(expected)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), expected)


# Verifying against this when the email is unknown keeps response time independent of
# whether an account exists.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def new_session_token() -> tuple[str, str]:
    """``(token for the cookie, hash for storage)``."""
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_patient_id() -> str:
    return f"p-{secrets.token_hex(5)}"


@dataclass
class LoginThrottle:
    """Lock an email after ``max_failures`` failed logins within ``window_s``.

    In-memory and per process: a brake on online guessing, not an audit trail.
    """

    max_failures: int = 5
    window_s: float = 15 * 60
    _failures: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.window_s]
        self._failures[key] = recent
        return recent

    def retry_after(self, key: str, now: float | None = None) -> float:
        """Seconds until ``key`` may try again; 0 when not locked."""
        now = time.monotonic() if now is None else now
        with self._lock:
            recent = self._recent(key, now)
            if len(recent) < self.max_failures:
                return 0.0
            return max(0.0, self.window_s - (now - recent[0]))

    def failure(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._recent(key, now).append(now)

    def success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
