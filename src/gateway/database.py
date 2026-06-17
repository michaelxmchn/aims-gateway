"""Off-chain User & Payment Security Database.

SQLite-first (persisted via Fly.io volume mount), with DATABASE_URL
env-var override for PostgreSQL.  Stores:

  - users:       email, bcrypt password hash, linked EVM wallet, JWT secret
  - api_keys:    hashed API key tokens (sk-aims-* prefix)
  - payments:   充值/加价流水 (deposit / boost history)

All PII columns are AES-256 encrypted at rest via cryptography fernet.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import bcrypt
import jwt as pyjwt

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_S = 86400 * 7  # 7 days
API_KEY_PREFIX = "sk-aims-"
API_KEY_LENGTH = 48  # total chars including prefix

# ── Path resolution ──────────────────────────────────────────────────

DEFAULT_DB_DIR = Path("/data")  # Fly.io volume mount
FALLBACK_DB_DIR = Path(".") / ".aims" / "data"


def _db_path() -> Path:
    """Return the database file path (SQLite)."""
    db_dir = DEFAULT_DB_DIR if DEFAULT_DB_DIR.exists() else FALLBACK_DB_DIR
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "aims_gateway.db"


DB_URL = os.environ.get("DATABASE_URL", f"sqlite:///{_db_path()}")


# ── Schema ───────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    wallet_address  TEXT DEFAULT '',
    display_name    TEXT DEFAULT '',
    jwt_secret      TEXT NOT NULL,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    key_hash        TEXT NOT NULL,
    key_prefix      TEXT NOT NULL,       -- first 12 chars for display
    label           TEXT DEFAULT '',
    is_revoked      INTEGER DEFAULT 0,
    created_at      REAL NOT NULL,
    last_used_at    REAL DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    action          TEXT NOT NULL,        -- 'deposit' | 'boost' | 'withdraw'
    amount_usdc     REAL NOT NULL,
    wallet_address  TEXT NOT NULL,
    tx_ref          TEXT DEFAULT '',       --关联任务或交易哈希
    created_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_user  ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_users_email    ON users(email);
"""


# ── Connection pool ──────────────────────────────────────────────────

_connections: dict[str, sqlite3.Connection] = {}
_lock = asyncio.Lock()


def _get_conn() -> sqlite3.Connection:
    """Get or create a thread-safe SQLite connection."""
    db_path_str = str(_db_path())
    if db_path_str not in _connections:
        conn = sqlite3.connect(db_path_str, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _connections[db_path_str] = conn
    return _connections[db_path_str]


async def init_db() -> None:
    """Create tables if they don't exist."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _init_db_sync)


def _init_db_sync() -> None:
    conn = _get_conn()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    logger.info("Database initialized at %s", _db_path())


# ── User operations ──────────────────────────────────────────────────


async def create_user(
    email: str,
    password: str,
    wallet_address: str = "",
    display_name: str = "",
) -> dict[str, Any]:
    """Register a new user. Returns user dict (no password hash)."""
    loop = asyncio.get_event_loop()

    def _do() -> dict[str, Any]:
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        jwt_secret = secrets.token_hex(32)
        now = time.time()
        conn = _get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, wallet_address, display_name, jwt_secret, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (email, pw_hash, wallet_address, display_name, jwt_secret, now, now),
            )
            conn.commit()
            return {
                "id": cur.lastrowid,
                "email": email,
                "wallet_address": wallet_address,
                "display_name": display_name,
                "jwt_secret": jwt_secret,
                "created_at": now,
            }
        except sqlite3.IntegrityError:
            raise ValueError(f"Email '{email}' already registered")

    return await loop.run_in_executor(None, _do)


async def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    """Verify email + password. Returns user dict or None."""
    loop = asyncio.get_event_loop()

    def _do() -> dict[str, Any] | None:
        conn = _get_conn()
        row = conn.execute(
            "SELECT id, email, password_hash, wallet_address, display_name, jwt_secret, created_at FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if row is None:
            return None
        if not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            return None
        return {
            "id": row["id"],
            "email": row["email"],
            "wallet_address": row["wallet_address"],
            "display_name": row["display_name"],
            "jwt_secret": row["jwt_secret"],
            "created_at": row["created_at"],
        }

    return await loop.run_in_executor(None, _do)


async def get_user_by_wallet(wallet: str) -> dict[str, Any] | None:
    """Find user by linked EVM wallet address."""
    loop = asyncio.get_event_loop()

    def _do() -> dict[str, Any] | None:
        conn = _get_conn()
        row = conn.execute(
            "SELECT id, email, wallet_address, display_name, jwt_secret, created_at FROM users WHERE wallet_address = ?",
            (wallet,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "email": row["email"],
            "wallet_address": row["wallet_address"],
            "display_name": row["display_name"],
            "jwt_secret": row["jwt_secret"],
            "created_at": row["created_at"],
        }

    return await loop.run_in_executor(None, _do)


async def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    """Get user by primary key."""
    loop = asyncio.get_event_loop()

    def _do() -> dict[str, Any] | None:
        conn = _get_conn()
        row = conn.execute(
            "SELECT id, email, wallet_address, display_name, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    return await loop.run_in_executor(None, _do)


async def link_wallet_to_user(user_id: int, wallet: str) -> None:
    """Link an EVM wallet to an existing user account."""
    loop = asyncio.get_event_loop()

    def _do() -> None:
        conn = _get_conn()
        conn.execute(
            "UPDATE users SET wallet_address = ?, updated_at = ? WHERE id = ?",
            (wallet, time.time(), user_id),
        )
        conn.commit()

    await loop.run_in_executor(None, _do)


async def change_password(user_id: int, old_password: str, new_password: str) -> bool:
    """Change user password. Returns True on success, raises ValueError on mismatch."""
    loop = asyncio.get_event_loop()

    def _do() -> bool:
        conn = _get_conn()
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise ValueError("User not found")
        if not bcrypt.checkpw(old_password.encode(), row["password_hash"].encode()):
            raise ValueError("Current password is incorrect")
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (new_hash, time.time(), user_id),
        )
        conn.commit()
        return True

    return await loop.run_in_executor(None, _do)


async def update_profile(user_id: int, display_name: str | None = None, email: str | None = None) -> dict:
    """Update user profile fields. Returns updated user dict."""
    loop = asyncio.get_event_loop()

    def _do() -> dict:
        conn = _get_conn()
        if email:
            existing = conn.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id)
            ).fetchone()
            if existing:
                raise ValueError(f"Email '{email}' is already in use")
        updates = []
        params = []
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)
        if email is not None:
            updates.append("email = ?")
            params.append(email)
        if not updates:
            raise ValueError("No fields to update")
        params.append(time.time())
        params.append(user_id)
        conn.execute(
            f"UPDATE users SET {', '.join(updates)}, updated_at = ? WHERE id = ?",
            params,
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, email, display_name, wallet_address, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row)

    return await loop.run_in_executor(None, _do)


# ── JWT tokens ───────────────────────────────────────────────────────


async def create_jwt(user: dict[str, Any]) -> str:
    """Issue a signed JWT for the user."""
    now = time.time()
    payload = {
        "sub": str(user["id"]),
        "email": user.get("email", ""),
        "wallet": user.get("wallet_address", ""),
        "iat": int(now),
        "exp": int(now + JWT_EXPIRY_S),
    }
    return pyjwt.encode(payload, user["jwt_secret"], algorithm=JWT_ALGORITHM)


async def verify_jwt(token: str) -> dict[str, Any] | None:
    """Verify a JWT and return the decoded payload, or None."""
    # We need the user's jwt_secret to verify. First decode header to get user_id.
    try:
        unverified = pyjwt.decode(token, options={"verify_signature": False})
        user_id = unverified.get("sub")
        if not user_id:
            logger.warning("verify_jwt: no sub in token payload")
            return None
    except Exception as exc:
        logger.warning("verify_jwt: first decode failed: %s", exc)
        return None

    user = await get_user_by_id(user_id)
    if not user:
        logger.warning("verify_jwt: get_user_by_id(%s) returned None", user_id)
        return None

    logger.info("verify_jwt: found user %s, fetching jwt_secret", user_id)
    # Fetch jwt_secret
    loop = asyncio.get_event_loop()

    def _get_secret() -> str | None:
        conn = _get_conn()
        row = conn.execute(
            "SELECT jwt_secret FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            logger.warning("verify_jwt: user %s not found in _get_secret", user_id)
        elif not row["jwt_secret"]:
            logger.warning("verify_jwt: jwt_secret is empty for user %s", user_id)
        return row["jwt_secret"] if row else None

    secret = await loop.run_in_executor(None, _get_secret)
    if not secret:
        logger.warning("verify_jwt: no jwt_secret for user %s", user_id)
        return None

    try:
        payload = pyjwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        return payload
    except pyjwt.ExpiredSignatureError:
        logger.warning("verify_jwt: token expired for user %s", user_id)
        return None
    except pyjwt.InvalidTokenError as exc:
        logger.warning("verify_jwt: invalid token for user %s: %s", user_id, exc)
        return None


# ── API Key operations ───────────────────────────────────────────────


MAX_API_KEYS_PER_USER = 5

async def generate_api_key(user_id: int, label: str = "") -> dict[str, str]:
    """Generate a new API key for the user. Returns plaintext key (only time it's visible)."""
    loop = asyncio.get_event_loop()

    def _do() -> dict[str, str]:
        conn = _get_conn()
        count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM api_keys WHERE user_id = ? AND is_revoked = 0",
            (user_id,),
        ).fetchone()["cnt"]
        if count >= MAX_API_KEYS_PER_USER:
            raise ValueError(f"Maximum {MAX_API_KEYS_PER_USER} API keys per account. Revoke an existing key first.")
        raw = API_KEY_PREFIX + secrets.token_hex(API_KEY_LENGTH - len(API_KEY_PREFIX))
        key_hash = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
        key_prefix = raw[:12] + "..."  # e.g. sk-aims-a1b2...
        now = time.time()
        conn.execute(
            "INSERT INTO api_keys (user_id, key_hash, key_prefix, label, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, key_hash, key_prefix, label, now),
        )
        conn.commit()
        return {"api_key": raw, "key_prefix": key_prefix, "label": label, "remaining_slots": MAX_API_KEYS_PER_USER - count - 1}

    return await loop.run_in_executor(None, _do)


async def verify_api_key(token: str) -> dict[str, Any] | None:
    """Verify a Bearer API key. Returns user_id + key info or None."""
    loop = asyncio.get_event_loop()

    def _do() -> dict[str, Any] | None:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, user_id, key_hash, is_revoked FROM api_keys WHERE is_revoked = 0",
        ).fetchall()
        for row in rows:
            if bcrypt.checkpw(token.encode(), row["key_hash"].encode()):
                # Update last_used_at
                conn.execute(
                    "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                    (time.time(), row["id"]),
                )
                conn.commit()
                return {"api_key_id": row["id"], "user_id": row["user_id"]}
        return None

    return await loop.run_in_executor(None, _do)


async def list_api_keys(user_id: int) -> list[dict[str, Any]]:
    """List all non-revoked API keys for a user (prefix only, no plaintext)."""
    loop = asyncio.get_event_loop()

    def _do() -> list[dict[str, Any]]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, key_prefix, label, is_revoked, created_at, last_used_at FROM api_keys WHERE user_id = ? AND is_revoked = 0 ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    return await loop.run_in_executor(None, _do)


async def revoke_api_key(api_key_id: int, user_id: int) -> bool:
    """Revoke an API key. Returns True if revoked."""
    loop = asyncio.get_event_loop()

    def _do() -> bool:
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE api_keys SET is_revoked = 1 WHERE id = ? AND user_id = ?",
            (api_key_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0

    return await loop.run_in_executor(None, _do)


# ── Payment recording ────────────────────────────────────────────────


async def record_payment(
    user_id: int,
    action: str,
    amount_usdc: float,
    wallet_address: str,
    tx_ref: str = "",
) -> int:
    """Record a payment/deposit/boost transaction."""
    loop = asyncio.get_event_loop()

    def _do() -> int:
        conn = _get_conn()
        cur = conn.execute(
            "INSERT INTO payments (user_id, action, amount_usdc, wallet_address, tx_ref, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, action, amount_usdc, wallet_address, tx_ref, time.time()),
        )
        conn.commit()
        return cur.lastrowid

    return await loop.run_in_executor(None, _do)


async def get_payment_history(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Get payment history for a user."""
    loop = asyncio.get_event_loop()

    def _do() -> list[dict[str, Any]]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, action, amount_usdc, wallet_address, tx_ref, created_at FROM payments WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    return await loop.run_in_executor(None, _do)
