"""Tiny database layer: SQLite for local development, PostgreSQL (psycopg 3) when DATABASE_URL is set.

All tables use the `nx_` prefix and are created with CREATE TABLE IF NOT EXISTS, so starting the app never
modifies or deletes any pre-existing table or row in your database.
"""
import os
import sqlite3
from contextlib import contextmanager

from . import config

IS_PG = config.DATABASE_URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = os.getenv("SQLITE_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "neural.db"))


def _pg_url() -> str:
    url = config.DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


@contextmanager
def connect():
    """Yield a connection; commits on success, rolls back on error."""
    if IS_PG:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(_pg_url(), row_factory=dict_row)
    else:
        os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
        conn = sqlite3.connect(SQLITE_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sql(sql: str) -> str:
    return sql.replace("?", "%s") if IS_PG else sql


def execute(sql: str, params=()):
    with connect() as c:
        cur = c.execute(_sql(sql), tuple(params))
        return cur.rowcount


def query(sql: str, params=()):
    with connect() as c:
        cur = c.execute(_sql(sql), tuple(params))
        return [dict(r) for r in cur.fetchall()]


def one(sql: str, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


# Ordered, append-only migrations. Never edit an applied one; add a new entry instead.
MIGRATIONS = [
    (1, [
        """CREATE TABLE IF NOT EXISTS nx_users (
            id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            password_hash TEXT NOT NULL, email_verified INTEGER NOT NULL DEFAULT 0, created_at BIGINT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS nx_chats (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
            created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS nx_chats_user ON nx_chats(user_id, updated_at)",
        """CREATE TABLE IF NOT EXISTS nx_messages (
            id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, user_id TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at BIGINT NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS nx_messages_chat ON nx_messages(chat_id, created_at)",
        """CREATE TABLE IF NOT EXISTS nx_memories (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, content TEXT NOT NULL, created_at BIGINT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS nx_usage (
            user_id TEXT NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL,
            requests INTEGER NOT NULL DEFAULT 0, chars INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, day, kind))""",
    ]),
    (2, [
        """CREATE TABLE IF NOT EXISTS nx_email_codes (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, code_hash TEXT NOT NULL,
            expires_at BIGINT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            used INTEGER NOT NULL DEFAULT 0, created_at BIGINT NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS nx_email_codes_user ON nx_email_codes(user_id, created_at)",
    ]),
    (3, [
        """CREATE TABLE IF NOT EXISTS nx_api_keys (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, prefix TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE, created_at BIGINT NOT NULL,
            last_used_at BIGINT, revoked_at BIGINT)""",
        "CREATE INDEX IF NOT EXISTS nx_api_keys_user ON nx_api_keys(user_id, created_at)",
    ]),
    # Username + password sign-in: email verification is no longer used, so unlock existing accounts.
    (4, [
        "UPDATE nx_users SET email_verified = 1",
    ]),
    # Token metering: tokens used per day, per account (chat) or per API key.
    (5, [
        "ALTER TABLE nx_usage ADD COLUMN tokens INTEGER NOT NULL DEFAULT 0",
    ]),
]


def migrate():
    """Apply pending migrations. Safe to run on every startup."""
    with connect() as c:
        c.execute("CREATE TABLE IF NOT EXISTS nx_migrations (version INTEGER PRIMARY KEY, applied_at BIGINT NOT NULL)")
    import time
    done = {r["version"] for r in query("SELECT version FROM nx_migrations")}
    for version, statements in MIGRATIONS:
        if version in done:
            continue
        with connect() as c:
            for st in statements:
                c.execute(st)
            c.execute(_sql("INSERT INTO nx_migrations (version, applied_at) VALUES (?, ?)"), (version, int(time.time())))
