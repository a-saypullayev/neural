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
MAX_ACTIVE_KEYS = _int("MAX_ACTIVE_KEYS", 10)

SESSION_DAYS = 14
ON_RENDER = bool(os.getenv("RENDER"))
SECURE_COOKIES = _bool("SECURE_COOKIES", ON_RENDER)
