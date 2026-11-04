"""Configuration, read from environment variables (and a local .env file if present)."""
import os

try:  # python-dotenv is optional at import time
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


APP_SECRET = os.getenv("APP_SECRET", "")
if APP_SECRET.startswith("replace-with"):  # the placeholder from .env.example is not a secret
    APP_SECRET = ""
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# AI provider (any OpenAI-compatible endpoint; Ollama by default)
AI_BASE_URL = os.getenv("AI_BASE_URL", "http://127.0.0.1:11434/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "ollama")
AI_MODEL = os.getenv("AI_MODEL", "qwen3.5:4b")
AI_PUBLIC_MODEL = os.getenv("AI_PUBLIC_MODEL", "neural-1")
AI_TIMEOUT = _int("AI_TIMEOUT", 180)
AI_REASONING_EFFORT = os.getenv("AI_REASONING_EFFORT", "").strip()  # e.g. "none" to skip thinking on Ollama


# Verification codes
CODE_TTL_SECONDS = 10 * 60
CODE_RESEND_COOLDOWN = _int("CODE_RESEND_COOLDOWN", 60)
CODE_MAX_PER_HOUR = _int("CODE_MAX_PER_HOUR", 5)
CODE_MAX_ATTEMPTS = 5

# Email (Mailjet). When all three are set, new accounts must verify an email address.
MAILJET_API_KEY = os.getenv("MAILJET_API_KEY", "").strip()
MAILJET_SECRET_KEY = os.getenv("MAILJET_SECRET_KEY", "").strip()
MAIL_FROM = os.getenv("MAIL_FROM", "").strip()
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "Neural AI").strip()
REQUIRE_EMAIL = _bool("REQUIRE_EMAIL", bool(MAILJET_API_KEY and MAILJET_SECRET_KEY and MAIL_FROM))
SIGNUPS_PER_IP_HOUR = _int("SIGNUPS_PER_IP_HOUR", 5)
# Extra comma-separated email domains to refuse (added to the built-in throwaway-mail list).
EXTRA_BLOCKED_EMAIL_DOMAINS = {d.strip().lower() for d in os.getenv("EXTRA_BLOCKED_EMAIL_DOMAINS", "").split(",") if d.strip()}

# Web chat limits
DAILY_REQUESTS = _int("DAILY_REQUESTS", 25)
DAILY_INPUT_CHARS = _int("DAILY_INPUT_CHARS", 15000)
MAX_MESSAGE_CHARS = _int("MAX_MESSAGE_CHARS", 8000)
MAX_OUTPUT_TOKENS = _int("MAX_OUTPUT_TOKENS", 1024)

# API limits
API_RATE_LIMIT_PER_MIN = _int("API_RATE_LIMIT_PER_MIN", 30)
API_DAILY_REQUESTS = _int("API_DAILY_REQUESTS", 500)
API_MAX_OUTPUT_TOKENS = _int("API_MAX_OUTPUT_TOKENS", 2048)
API_MAX_INPUT_CHARS = _int("API_MAX_INPUT_CHARS", 32000)
API_MAX_MESSAGES = _int("API_MAX_MESSAGES", 50)

# Optional: the public address of this site (e.g. https://neural-6mzi.onrender.com). Used for the Windows app download.
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
# Plans. Only "free" exists for now; a future paid plan just becomes another entry here.
PLANS = {
    "free": {
        "name": "Free",
        "chat_tokens_per_day": _int("FREE_CHAT_TOKENS_PER_DAY", 10000),      # web chat, per account
        "max_active_keys": _int("FREE_MAX_ACTIVE_KEYS", 3),                  # API keys alive at once
        "keys_per_day": _int("FREE_KEYS_PER_DAY", 3),                        # API keys created per UTC day
        "tokens_per_key_per_day": _int("FREE_TOKENS_PER_KEY_PER_DAY", 10000),  # each API key's own allowance
    },
}
DEFAULT_PLAN = "free"
SESSION_DAYS = 14
ON_RENDER = bool(os.getenv("RENDER"))
SECURE_COOKIES = _bool("SECURE_COOKIES", ON_RENDER)
