"""SQLite-backed persistence for channels, memberships, and chat messages."""

import datetime
import os
import sqlite3
import threading

from env_loader import load_dotenv


load_dotenv()


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


DEFAULT_DB_PATH = os.path.join(_project_root(), "db", "asynaprous.sqlite3")


def get_db_path():
    configured = os.environ.get("ASYNAPROUS_DB_PATH", "").strip()
    if not configured:
        return DEFAULT_DB_PATH

    if os.path.isabs(configured):
        return configured

    return os.path.join(_project_root(), configured)


DB_PATH = get_db_path()

_db_lock = threading.Lock()
_initialized = False


def _connect():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return sqlite3.connect(db_path, timeout=30, check_same_thread=False)


def initialize_message_store():
    """Create channel/message tables and seed default channels if missing."""
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
            CREATE TABLE IF NOT EXISTS channels (
                name TEXT PRIMARY KEY,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_members (
                channel_name TEXT NOT NULL,
                username TEXT NOT NULL,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (channel_name, username),
                FOREIGN KEY(channel_name) REFERENCES channels(name)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_name TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(channel_name) REFERENCES channels(name)
            )
            """
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_channel_id ON messages(channel_name, id)"
        )

        conn.commit()
        conn.close()
        _initialized = True


def get_channels():
    """Return available channel names."""
    initialize_message_store()
    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT name FROM channels ORDER BY name ASC")
        rows = cur.fetchall()
        conn.close()
    return [row[0] for row in rows]


def create_channel(channel_name, creator="me"):
    """Create a new channel and register creator as a member."""
    initialize_message_store()

    safe_channel = str(channel_name or "").strip()
    safe_creator = str(creator or "me").strip()
    if not safe_channel:
        return False, "invalid-channel"

    now = datetime.datetime.utcnow().isoformat() + "Z"
    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT name FROM channels WHERE name = ?", (safe_channel,))
        existed = cur.fetchone() is not None

        if not existed:
            cur.execute(
                """
                INSERT INTO channels (name, created_by, created_at)
                VALUES (?, ?, ?)
                """,
                (safe_channel, safe_creator or "me", now),
            )

        cur.execute(
            """
            INSERT OR IGNORE INTO channel_members (channel_name, username, joined_at)
            VALUES (?, ?, ?)
            """,
            (safe_channel, safe_creator or "me", now),
        )
        conn.commit()
        conn.close()

    return not existed, safe_channel


def join_channel(channel_name, user="me"):
    """Register user membership for an existing channel."""
    initialize_message_store()

    safe_channel = str(channel_name or "").strip()
    safe_user = str(user or "me").strip()
    if not safe_channel:
        return False, "invalid-channel"

    now = datetime.datetime.utcnow().isoformat() + "Z"
    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM channels WHERE name = ?", (safe_channel,))
        if cur.fetchone() is None:
            conn.close()
            return False, "channel-not-found"

        cur.execute(
            """
            INSERT OR IGNORE INTO channel_members (channel_name, username, joined_at)
            VALUES (?, ?, ?)
            """,
            (safe_channel, safe_user or "me", now),
        )
        conn.commit()
        conn.close()

    return True, safe_channel


def rename_channel(channel_name, new_channel_name, user=""):
    """Rename one channel when requesting user is a member."""
    initialize_message_store()

    old_name = str(channel_name or "").strip()
    new_name = str(new_channel_name or "").strip()
    safe_user = str(user or "").strip()

    if not old_name or not new_name:
        return False, "invalid-channel"
    if old_name == new_name:
        return True, new_name
    if not safe_user:
        return False, "forbidden"

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM channels WHERE name = ?", (old_name,))
        if cur.fetchone() is None:
            conn.close()
            return False, "channel-not-found"

        cur.execute(
            "SELECT 1 FROM channel_members WHERE channel_name = ? AND username = ?",
            (old_name, safe_user),
        )
        if cur.fetchone() is None:
            conn.close()
            return False, "forbidden"

        cur.execute("SELECT 1 FROM channels WHERE name = ?", (new_name,))
        if cur.fetchone() is not None:
            conn.close()
            return False, "channel-exists"

        cur.execute("UPDATE channels SET name = ? WHERE name = ?", (new_name, old_name))
        cur.execute(
            "UPDATE channel_members SET channel_name = ? WHERE channel_name = ?",
            (new_name, old_name),
        )
        cur.execute(
            "UPDATE messages SET channel_name = ? WHERE channel_name = ?",
            (new_name, old_name),
        )
        conn.commit()
        conn.close()

    return True, new_name


def leave_channel(channel_name, user=""):
    """Remove user membership from channel and cleanup empty channels."""
    initialize_message_store()

    safe_channel = str(channel_name or "").strip()
    safe_user = str(user or "").strip()
    if not safe_channel:
        return False, "invalid-channel"
    if not safe_user:
        return False, "forbidden"

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM channels WHERE name = ?", (safe_channel,))
        if cur.fetchone() is None:
            conn.close()
            return False, "channel-not-found"

        cur.execute(
            "SELECT 1 FROM channel_members WHERE channel_name = ? AND username = ?",
            (safe_channel, safe_user),
        )
        if cur.fetchone() is None:
            conn.close()
            return False, "not-member"

        cur.execute(
            "DELETE FROM channel_members WHERE channel_name = ? AND username = ?",
            (safe_channel, safe_user),
        )

        cur.execute(
            "SELECT COUNT(*) FROM channel_members WHERE channel_name = ?",
            (safe_channel,),
        )
        member_count = int(cur.fetchone()[0])
        removed_channel = member_count == 0
        if removed_channel:
            cur.execute("DELETE FROM messages WHERE channel_name = ?", (safe_channel,))
            cur.execute("DELETE FROM channels WHERE name = ?", (safe_channel,))

        conn.commit()
        conn.close()

    return True, {"channel": safe_channel, "removed_channel": removed_channel}


def get_user_channels(user=""):
    """Return channels joined by user."""
    initialize_message_store()
    safe_user = str(user or "").strip()

    if not safe_user:
        return []

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT channel_name
            FROM channel_members
            WHERE username = ?
            ORDER BY channel_name ASC
            """,
            (safe_user,),
        )
        rows = cur.fetchall()
        conn.close()

    return [row[0] for row in rows]


def get_channel_members(channel_name):
    """Return usernames currently joined to a channel."""
    initialize_message_store()

    safe_channel = str(channel_name or "").strip()
    if not safe_channel:
        return []

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT username
            FROM channel_members
            WHERE channel_name = ?
            ORDER BY username ASC
            """,
            (safe_channel,),
        )
        rows = cur.fetchall()
        conn.close()

    return [str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()]


def is_channel_member(channel_name, user):
    """Return True only when user is a member of channel."""
    initialize_message_store()

    safe_channel = str(channel_name or "").strip()
    safe_user = str(user or "").strip()
    if not safe_channel or not safe_user:
        return False

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1
            FROM channel_members
            WHERE channel_name = ? AND username = ?
            LIMIT 1
            """,
            (safe_channel, safe_user),
        )
        found = cur.fetchone() is not None
        conn.close()

    return found


def get_messages(channel_name):
    """Return message history for one channel in append order."""
    initialize_message_store()

    safe_channel = str(channel_name or "general").strip() or "general"
    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT sender, message, created_at
            FROM messages
            WHERE channel_name = ?
            ORDER BY id ASC
            """,
            (safe_channel,),
        )
        rows = cur.fetchall()
        conn.close()

    result = []
    for sender, message, created_at in rows:
        display_time = created_at[11:19] if len(created_at) >= 19 else created_at
        result.append(
            {
                "sender": sender,
                "message": message,
                "timestamp": display_time,
            }
        )
    return result


def add_message(channel_name, sender, message):
    """Insert immutable message record and ensure sender membership."""
    initialize_message_store()

    safe_channel = str(channel_name or "general").strip() or "general"
    safe_sender = str(sender or "anonymous").strip() or "anonymous"
    safe_message = str(message or "")
    now = datetime.datetime.utcnow().isoformat() + "Z"

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT OR IGNORE INTO channels (name, created_by, created_at)
            VALUES (?, ?, ?)
            """,
            (safe_channel, safe_sender, now),
        )
        cur.execute(
            """
            INSERT OR IGNORE INTO channel_members (channel_name, username, joined_at)
            VALUES (?, ?, ?)
            """,
            (safe_channel, safe_sender, now),
        )
        cur.execute(
            """
            INSERT INTO messages (channel_name, sender, message, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (safe_channel, safe_sender, safe_message, now),
        )

        conn.commit()
        conn.close()

    return {
        "sender": safe_sender,
        "message": safe_message,
        "timestamp": now[11:19],
    }


def reset_message_store_runtime_state():
    """Reset in-memory initialization state to force a fresh setup call."""
    global _initialized

    with _db_lock:
        _initialized = False
