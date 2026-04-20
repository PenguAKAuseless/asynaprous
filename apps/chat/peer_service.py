"""Persistent thread-safe storage for known peer endpoints."""

import datetime
import os
import sqlite3
import threading

from apps.auth.account_store import get_db_path

_db_lock = threading.Lock()
_initialized = False


def _connect():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return sqlite3.connect(db_path, timeout=30, check_same_thread=False)


def initialize_peer_store():
    """Ensure known peer table exists."""
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
            CREATE TABLE IF NOT EXISTS known_peers (
                peer_id TEXT PRIMARY KEY,
                ip TEXT NOT NULL,
                port INTEGER NOT NULL,
                owner_username TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

        _initialized = True


def reset_peer_store_runtime_state():
    """Reset in-memory initialization state for tests/admin purge."""
    global _initialized

    with _db_lock:
        _initialized = False


def add_peer_info(peer_id, ip, port, owner_username=""):
    """Add or update peer endpoint information."""
    safe_peer_id = str(peer_id or "").strip()
    safe_ip = str(ip or "").strip()
    safe_owner = str(owner_username or "").strip()
    if not safe_peer_id or not safe_ip or port is None:
        return False

    try:
        safe_port = int(port)
    except (TypeError, ValueError):
        return False

    if safe_port <= 0 or safe_port > 65535:
        return False

    initialize_peer_store()
    now = datetime.datetime.utcnow().isoformat() + "Z"

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO known_peers (peer_id, ip, port, owner_username, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(peer_id) DO UPDATE SET
                ip = excluded.ip,
                port = excluded.port,
                owner_username = CASE
                    WHEN excluded.owner_username <> '' THEN excluded.owner_username
                    ELSE known_peers.owner_username
                END,
                updated_at = excluded.updated_at
            """,
            (safe_peer_id, safe_ip, safe_port, safe_owner, now),
        )
        conn.commit()
        conn.close()

    return True


def get_peer_info(peer_id):
    """Return endpoint info for one peer id."""
    safe_peer_id = str(peer_id or "").strip()
    if not safe_peer_id:
        return None

    initialize_peer_store()

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ip, port, owner_username, updated_at
            FROM known_peers
            WHERE peer_id = ?
            """,
            (safe_peer_id,),
        )
        row = cur.fetchone()
        conn.close()

    if not row:
        return None

    return {
        "ip": str(row[0]),
        "port": int(row[1]),
        "owner_username": str(row[2] or ""),
        "updated_at": str(row[3] or ""),
    }


def get_all_peers():
    """Return a copy of all known peers keyed by peer id."""
    initialize_peer_store()

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT peer_id, ip, port, owner_username, updated_at
            FROM known_peers
            ORDER BY peer_id ASC
            """
        )
        rows = cur.fetchall()
        conn.close()

    peers = {}
    for peer_id, ip, port, owner_username, updated_at in rows:
        peers[str(peer_id)] = {
            "ip": str(ip),
            "port": int(port),
            "owner_username": str(owner_username or ""),
            "updated_at": str(updated_at or ""),
        }
    return peers