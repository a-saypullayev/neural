"""Password hashing, signed session tokens, API key and verification-code helpers."""
import base64
import hashlib
import hmac
import secrets
import time

from . import config

PBKDF2_ITERATIONS = 260_000


def _secret() -> bytes:
    if not config.APP_SECRET:
        raise RuntimeError("APP_SECRET is not set. Generate one: python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
    return config.APP_SECRET.encode()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
        return hmac.compare_digest(calc, digest)
    except Exception:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def sign_session(user_id: str, days: int = config.SESSION_DAYS) -> str:
    exp = int(time.time()) + days * 86400
    payload = f"{user_id}.{exp}"
    sig = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_session(token: str):
    """Return the user id for a valid, unexpired token, else None."""
    try:
        user_id, exp, sig = token.rsplit(".", 2)
        payload = f"{user_id}.{exp}"
        good = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        if int(exp) < time.time():
            return None
        return user_id
    except Exception:
        return None


KEY_PREFIX = "nrl_"


def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    # API keys are long random strings, so plain SHA-256 is appropriate (and allows indexed lookup).
    return hashlib.sha256(key.encode()).hexdigest()


def key_display_prefix(key: str) -> str:
    return key[:8]


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(user_id: str, code: str) -> str:
    return hmac.new(_secret(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def new_id() -> str:
    return secrets.token_hex(12)


def new_ordered_id() -> str:
    """Time-ordered id (nanosecond timestamp + random suffix) so rows sort in insertion order."""
    return f"{time.time_ns():020d}{secrets.token_hex(4)}"
