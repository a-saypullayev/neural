"""Business logic (accounts, verification codes, API keys, chats, usage). No web framework imports."""
import re
import time
from datetime import datetime, timezone

from . import config, db, security


class ServiceError(Exception):
    def __init__(self, message, status=400, code="bad_request", retry_after=None):
        super().__init__(message)
        self.message, self.status, self.code, self.retry_after = message, status, code, retry_after


USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,29}$")


def now() -> int:
    return int(time.time())


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- accounts
def public_user(u: dict) -> dict:
    # The legacy `email` column now stores the username (no email is collected or sent).
    return {"id": u["id"], "username": u["email"], "name": u["name"], "email_verified": True}


def register(username: str, password: str, name: str = "") -> dict:
    username = (username or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ServiceError("Username must be 3-30 characters: letters, numbers, dot, dash or underscore.", 400, "invalid_username")
    if not (8 <= len(password or "") <= 200):
        raise ServiceError("Password must be 8-200 characters.", 400, "weak_password")
    if db.one("SELECT id FROM nx_users WHERE email = ?", (username,)):
        raise ServiceError("That username is already taken.", 409, "username_taken")
    uid = security.new_id()
    try:
        db.execute(
            "INSERT INTO nx_users (id, email, name, password_hash, email_verified, created_at) VALUES (?,?,?,?,1,?)",
            (uid, username, (name or username).strip()[:60], security.hash_password(password), now()),
        )
    except Exception:
        raise ServiceError("That username is already taken.", 409, "username_taken")
    return db.one("SELECT * FROM nx_users WHERE id = ?", (uid,))


def authenticate(username: str, password: str) -> dict:
    u = db.one("SELECT * FROM nx_users WHERE email = ?", ((username or "").strip().lower(),))
    ok = security.verify_password(password or "", u["password_hash"]) if u else security.verify_password(password or "", "x$0$0$0")
    if not u or not ok:
        raise ServiceError("Incorrect username or password.", 401, "invalid_credentials")
    return u


def get_user(user_id: str):
    return db.one("SELECT * FROM nx_users WHERE id = ?", (user_id,))


# ------------------------------------------------------ email verification
def issue_code(user: dict) -> str:
    """Create a new 6-digit code (invalidating older ones). Enforces cooldown and hourly cap."""
    if user["email_verified"]:
        raise ServiceError("This email is already verified.", 400, "already_verified")
    t = now()
    last = db.one("SELECT created_at FROM nx_email_codes WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user["id"],))
    if last and t - last["created_at"] < config.CODE_RESEND_COOLDOWN:
        wait = config.CODE_RESEND_COOLDOWN - (t - last["created_at"])
        raise ServiceError(f"Please wait {wait}s before requesting another code.", 429, "code_cooldown", retry_after=wait)
    n = db.one("SELECT COUNT(*) AS n FROM nx_email_codes WHERE user_id = ? AND created_at > ?", (user["id"], t - 3600))["n"]
    if n >= config.CODE_MAX_PER_HOUR:
        raise ServiceError("Too many verification emails requested. Try again in an hour.", 429, "code_rate_limited", retry_after=3600)
    db.execute("UPDATE nx_email_codes SET used = 1 WHERE user_id = ? AND used = 0", (user["id"],))
    code = security.generate_code()
    db.execute(
        "INSERT INTO nx_email_codes (id, user_id, code_hash, expires_at, attempts, used, created_at) VALUES (?,?,?,?,0,0,?)",
        (security.new_id(), user["id"], security.hash_code(user["id"], code), t + config.CODE_TTL_SECONDS, t),
    )
    return code


def cancel_latest_code(user_id: str):
    """Used when the email could not be sent, so the failed attempt does not burn the user's cooldown."""
    db.execute("DELETE FROM nx_email_codes WHERE user_id = ? AND created_at = (SELECT MAX(created_at) FROM nx_email_codes WHERE user_id = ?)", (user_id, user_id))


def verify_code(user: dict, code: str) -> None:
    import hmac
    if user["email_verified"]:
        return
    code = (code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise ServiceError("Enter the 6-digit code.", 400, "invalid_code")
    row = db.one("SELECT * FROM nx_email_codes WHERE user_id = ? AND used = 0 ORDER BY created_at DESC LIMIT 1", (user["id"],))
    if not row:
        raise ServiceError("No active code. Request a new one.", 400, "no_active_code")
    if row["expires_at"] < now():
        raise ServiceError("This code has expired. Request a new one.", 400, "code_expired")
    if row["attempts"] >= config.CODE_MAX_ATTEMPTS:
        raise ServiceError("Too many incorrect attempts. Request a new code.", 429, "too_many_attempts")
    if not hmac.compare_digest(row["code_hash"], security.hash_code(user["id"], code)):
        db.execute("UPDATE nx_email_codes SET attempts = attempts + 1 WHERE id = ?", (row["id"],))
        raise ServiceError("Incorrect code.", 400, "incorrect_code")
    db.execute("UPDATE nx_email_codes SET used = 1 WHERE id = ?", (row["id"],))
    db.execute("UPDATE nx_users SET email_verified = 1 WHERE id = ?", (user["id"],))


# ---------------------------------------------------------------- API keys
def public_key(k: dict, limit: int = 0) -> dict:
    used = token_usage("key:" + k["id"], "api")
    return {"id": k["id"], "name": k["name"], "prefix": k["prefix"], "created_at": k["created_at"],
            "last_used_at": k["last_used_at"], "revoked": k["revoked_at"] is not None,
            "tokens_used": used, "token_limit": limit}


def create_key(user: dict, name: str):
    limits = plan_limits(user)
    name = (name or "").strip()
    if not (1 <= len(name) <= 60):
        raise ServiceError("Give the key a name (1-60 characters).", 400, "invalid_name")
    active = db.one("SELECT COUNT(*) AS n FROM nx_api_keys WHERE user_id = ? AND revoked_at IS NULL", (user["id"],))["n"]
    if active >= limits["max_active_keys"]:
        raise ServiceError(f"The {limits['name']} plan allows {limits['max_active_keys']} active API keys. Revoke one first.", 400, "key_limit")
    made_today = db.one("SELECT COUNT(*) AS n FROM nx_api_keys WHERE user_id = ? AND created_at >= ?", (user["id"], day_start()))["n"]
    if made_today >= limits["keys_per_day"]:
        raise ServiceError(f"The {limits['name']} plan allows creating {limits['keys_per_day']} API keys per day. Try again after 00:00 UTC.", 429, "key_daily_limit")
    plain = security.generate_api_key()
    kid = security.new_id()
    db.execute(
        "INSERT INTO nx_api_keys (id, user_id, name, prefix, key_hash, created_at) VALUES (?,?,?,?,?,?)",
        (kid, user["id"], name, security.key_display_prefix(plain), security.hash_api_key(plain), now()),
    )
    return public_key(db.one("SELECT * FROM nx_api_keys WHERE id = ?", (kid,)), limits["tokens_per_key_per_day"]), plain


def list_keys(user: dict):
    lim = plan_limits(user)["tokens_per_key_per_day"]
    return [public_key(k, lim) for k in db.query("SELECT * FROM nx_api_keys WHERE user_id = ? ORDER BY created_at DESC", (user["id"],))]


def revoke_key(user: dict, key_id: str) -> None:
    n = db.execute("UPDATE nx_api_keys SET revoked_at = ? WHERE id = ? AND user_id = ? AND revoked_at IS NULL", (now(), key_id, user["id"]))
    if not n:
        raise ServiceError("Key not found or already revoked.", 404, "key_not_found")


def authenticate_key(plain: str):
    """Return (user, key_row) for a valid active key owned by a verified user, else None."""
    if not plain or not plain.startswith(security.KEY_PREFIX) or len(plain) > 200:
        return None
    k = db.one("SELECT * FROM nx_api_keys WHERE key_hash = ?", (security.hash_api_key(plain),))
    if not k or k["revoked_at"] is not None:
        return None
    u = get_user(k["user_id"])
    if not u or not u["email_verified"]:
        return None
    if not k["last_used_at"] or now() - k["last_used_at"] > 60:
        db.execute("UPDATE nx_api_keys SET last_used_at = ? WHERE id = ?", (now(), k["id"]))
    return u, k


# ------------------------------------------------------------ plans + tokens
def plan_of(user: dict) -> str:
    """Which plan an account is on. Everyone is on the free plan for now; upgrades will hook in here."""
    return config.DEFAULT_PLAN


def plan_limits(user: dict) -> dict:
    return config.PLANS.get(plan_of(user), config.PLANS[config.DEFAULT_PLAN])


def est_tokens(text) -> int:
    """Rough token count (about 4 characters per token) used when the model does not report usage."""
    n = len(text) if isinstance(text, str) else int(text or 0)
    return (n + 3) // 4 if n > 0 else 0


def day_start() -> int:
    return int(datetime.strptime(today(), "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def token_usage(scope: str, kind: str) -> int:
    """Tokens used today by an account (kind 'chat') or an API key (scope 'key:<id>', kind 'api')."""
    row = db.one("SELECT tokens FROM nx_usage WHERE user_id = ? AND day = ? AND kind = ?", (scope, today(), kind))
    return row["tokens"] if row else 0


def add_tokens(scope: str, kind: str, tokens: int, requests: int = 1) -> None:
    day, tokens = today(), max(0, int(tokens))
    sql = "UPDATE nx_usage SET tokens = tokens + ?, requests = requests + ? WHERE user_id = ? AND day = ? AND kind = ?"
    if db.execute(sql, (tokens, requests, scope, day, kind)):
        return
    try:
        db.execute("INSERT INTO nx_usage (user_id, day, kind, requests, chars, tokens) VALUES (?,?,?,?,0,?)", (scope, day, kind, requests, tokens))
    except Exception:  # another request created the row first
        db.execute(sql, (tokens, requests, scope, day, kind))


def tokens_left(scope: str, kind: str, limit: int, needed: int, what: str):
    """Return how many tokens remain today, or raise 429 if nothing (or not enough for this input) is left."""
    left = limit - token_usage(scope, kind)
    if left <= 0:
        raise ServiceError(f"{what} has used all {limit:,} tokens for today. They reset at 00:00 UTC.", 429, "daily_limit")
    if needed >= left:
        raise ServiceError(f"This message is too long for the {left:,} tokens {what.lower()} has left today. Send a shorter one, or wait until 00:00 UTC.", 429, "daily_limit")
    return left


# ------------------------------------------------------------------- usage
def check_and_count(user_id: str, kind: str, chars: int, max_requests: int, max_chars=None) -> None:
    """Atomically-ish enforce a daily quota; counts the request on success."""
    day = today()
    row = db.one("SELECT requests, chars FROM nx_usage WHERE user_id = ? AND day = ? AND kind = ?", (user_id, day, kind))
    req, ch = (row["requests"], row["chars"]) if row else (0, 0)
    if req >= max_requests:
        raise ServiceError("Daily request limit reached. It resets at 00:00 UTC.", 429, "daily_limit")
    if max_chars is not None and ch + chars > max_chars:
        raise ServiceError("Daily input limit reached. It resets at 00:00 UTC.", 429, "daily_limit")
    if row:
        db.execute("UPDATE nx_usage SET requests = requests + 1, chars = chars + ? WHERE user_id = ? AND day = ? AND kind = ?", (chars, user_id, day, kind))
    else:
        db.execute("INSERT INTO nx_usage (user_id, day, kind, requests, chars) VALUES (?,?,?,1,?)", (user_id, day, kind, chars))


def usage_summary(user) -> dict:
    p = plan_limits(user)
    return {"plan": plan_of(user), "plan_name": p["name"],
            "tokens": token_usage(user["id"], "chat"), "token_limit": p["chat_tokens_per_day"]}


# ------------------------------------------------------------------- chats
def list_chats(user_id: str):
    return db.query("SELECT id, title, updated_at FROM nx_chats WHERE user_id = ? ORDER BY updated_at DESC LIMIT 200", (user_id,))


def get_chat(user_id: str, chat_id: str):
    return db.one("SELECT * FROM nx_chats WHERE id = ? AND user_id = ?", (chat_id, user_id))


def create_chat(user_id: str, title: str) -> str:
    cid, t = security.new_id(), now()
    db.execute("INSERT INTO nx_chats (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)", (cid, user_id, title[:80] or "New chat", t, t))
    return cid


def delete_chat(user_id: str, chat_id: str) -> bool:
    if not get_chat(user_id, chat_id):
        return False
    db.execute("DELETE FROM nx_messages WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    db.execute("DELETE FROM nx_chats WHERE id = ? AND user_id = ?", (chat_id, user_id))
    return True


def rename_chat(user_id: str, chat_id: str, title: str) -> bool:
    return bool(db.execute("UPDATE nx_chats SET title = ? WHERE id = ? AND user_id = ?", (title.strip()[:80] or "New chat", chat_id, user_id)))


def chat_messages(user_id: str, chat_id: str, limit=200):
    return db.query("SELECT role, content, created_at FROM nx_messages WHERE chat_id = ? AND user_id = ? ORDER BY id LIMIT ?", (chat_id, user_id, limit))


def add_message(user_id: str, chat_id: str, role: str, content: str):
    t = now()
    db.execute("INSERT INTO nx_messages (id, chat_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)", (security.new_ordered_id(), chat_id, user_id, role, content, t))
    db.execute("UPDATE nx_chats SET updated_at = ? WHERE id = ? AND user_id = ?", (t, chat_id, user_id))


# ---------------------------------------------------------------- memories
def list_memories(user_id: str):
    return db.query("SELECT id, content FROM nx_memories WHERE user_id = ? ORDER BY created_at", (user_id,))


def add_memory(user_id: str, content: str):
    content = (content or "").strip()
    if not (1 <= len(content) <= 300):
        raise ServiceError("A memory must be 1-300 characters.", 400, "invalid_memory")
    if len(list_memories(user_id)) >= 50:
        raise ServiceError("Memory limit (50) reached. Delete one first.", 400, "memory_limit")
    mid = security.new_id()
    db.execute("INSERT INTO nx_memories (id, user_id, content, created_at) VALUES (?,?,?,?)", (mid, user_id, content, now()))
    return {"id": mid, "content": content}


def delete_memory(user_id: str, memory_id: str) -> bool:
    return bool(db.execute("DELETE FROM nx_memories WHERE id = ? AND user_id = ?", (memory_id, user_id)))


SYSTEM_PROMPT = (
    "You are Neural, a helpful, honest and concise AI assistant. Answer clearly. "
    "If you are unsure, say so rather than guessing."
)


def system_prompt_for(user_id: str, search_context: str = "") -> str:
    p = SYSTEM_PROMPT
    mem = list_memories(user_id)
    if mem:
        p += "\n\nThings the user asked you to remember:\n" + "\n".join(f"- {m['content']}" for m in mem)
    if search_context:
        p += "\n\nWeb search results (may be incomplete; cite sources by title when you use them):\n" + search_context
    return p
