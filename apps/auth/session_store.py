"""Session storage backed by SQLite so multiple processes share login state."""

import datetime
import os
import sqlite3
import threading
import time
import uuid

from env_loader import load_dotenv

from .account_store import get_db_path


load_dotenv()


SESSION_TTL_SECONDS = 3600

_db_lock = threading.Lock()
_initialized = False


def _connect():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return sqlite3.connect(db_path, timeout=30, check_same_thread=False)


def initialize_session_store():
    """Create shared auth session table if missing."""
    global _initialized

    if _initialized:
        return

    with _db_lock:
        if _initialized:
            return

        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                session_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at)"
        )
        conn.commit()
        conn.close()
        _initialized = True


def create_session(username, ttl_seconds=SESSION_TTL_SECONDS):
    """Create a new session and return generated session id."""
    initialize_session_store()

    safe_user = str(username or "").strip()
    if not safe_user:
        raise ValueError("username is required")

    session_id = str(uuid.uuid4())
    expires_at = time.time() + int(ttl_seconds)
    created_at = datetime.datetime.utcnow().isoformat() + "Z"

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO auth_sessions (session_id, username, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, safe_user, expires_at, created_at),
        )
        conn.commit()
        conn.close()

    return session_id


def get_session_user(session_id):
    """Return username for valid session, otherwise None."""
    initialize_session_store()

    safe_session_id = str(session_id or "").strip()
    if not safe_session_id:
        return None

    now = time.time()
    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT username, expires_at FROM auth_sessions WHERE session_id = ?",
            (safe_session_id,),
        )
        row = cur.fetchone()

        if not row:
            conn.close()
            return None

        username, expires_at = row
        if float(expires_at) <= now:
            cur.execute("DELETE FROM auth_sessions WHERE session_id = ?", (safe_session_id,))
            conn.commit()
            conn.close()
            return None

        conn.close()
        return username


def remove_session(session_id):
    """Delete session id from storage."""
    initialize_session_store()

    safe_session_id = str(session_id or "").strip()
    if not safe_session_id:
        return False

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM auth_sessions WHERE session_id = ?", (safe_session_id,))
        removed = cur.rowcount > 0
        conn.commit()
        conn.close()

    return removed


def cleanup_expired_sessions():
    """Remove all expired sessions and return removed count."""
    initialize_session_store()

    now = time.time()
    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now,))
        removed = cur.rowcount
        conn.commit()
        conn.close()

    return removed


def reset_session_store_runtime_state():
    """Reset in-memory initialization state to force fresh setup call."""
    global _initialized

    with _db_lock:
        _initialized = False


initialize_session_store()
