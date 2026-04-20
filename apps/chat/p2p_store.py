"""SQLite-backed local persistence for private and peer-to-peer conversations."""

import datetime
import json
import os
import sqlite3
import threading
import uuid

from env_loader import load_dotenv

from apps.auth.account_store import get_db_path


load_dotenv()


_db_lock = threading.Lock()
_initialized = False


def _connect():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return sqlite3.connect(db_path, timeout=30, check_same_thread=False)


def _now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"


def _safe_peer_list(peer_ids):
    if not isinstance(peer_ids, list):
        return []

    out = []
    seen = set()
    for peer in peer_ids:
        value = str(peer or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _direct_room_id(owner_username, peer_id):
    return "direct::{}::{}".format(owner_username, peer_id)


def initialize_p2p_store():
    """Create local p2p/private room tables if missing."""
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
            CREATE TABLE IF NOT EXISTS p2p_rooms (
                room_id TEXT PRIMARY KEY,
                owner_username TEXT NOT NULL,
                room_name TEXT NOT NULL,
                peers_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS p2p_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL,
                owner_username TEXT NOT NULL,
                peer_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                direction TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_p2p_rooms_owner ON p2p_rooms(owner_username, updated_at)"
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_p2p_messages_owner_room
            ON p2p_messages(owner_username, room_id, id)
            """
        )

        conn.commit()
        conn.close()
        _initialized = True


def _room_row_to_dict(row):
    room_id, room_name, peers_json, updated_at = row
    try:
        peers = json.loads(peers_json)
        if not isinstance(peers, list):
            peers = []
    except (TypeError, ValueError):
        peers = []

    room_type = "direct" if room_id.startswith("direct::") else "private"
    return {
        "room_id": room_id,
        "room_name": room_name,
        "peers": peers,
        "type": room_type,
        "updated_at": updated_at,
    }


def list_rooms(owner_username):
    """List rooms visible to one local user."""
    initialize_p2p_store()
    safe_owner = str(owner_username or "").strip()
    if not safe_owner:
        return []

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT room_id, room_name, peers_json, updated_at
            FROM p2p_rooms
            WHERE owner_username = ?
            ORDER BY updated_at DESC
            """,
            (safe_owner,),
        )
        rows = cur.fetchall()
        conn.close()

    return [_room_row_to_dict(row) for row in rows]


def _upsert_room(owner_username, room_id, room_name, peer_ids):
    peers = _safe_peer_list(peer_ids)
    now = _now_iso()
    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO p2p_rooms (
                room_id,
                owner_username,
                room_name,
                peers_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(room_id) DO UPDATE SET
                room_name=excluded.room_name,
                peers_json=excluded.peers_json,
                updated_at=excluded.updated_at
            """,
            (
                room_id,
                owner_username,
                room_name,
                json.dumps(peers),
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()


def create_private_room(owner_username, room_name, peer_ids):
    """Create a private multi-peer room in local storage."""
    initialize_p2p_store()

    safe_owner = str(owner_username or "").strip()
    safe_name = str(room_name or "").strip()
    peers = _safe_peer_list(peer_ids)

    if not safe_owner:
        return False, "Unauthorized", None
    if not safe_name:
        return False, "Room name is required", None
    if not peers:
        return False, "Select at least one peer", None

    room_id = "private::{}".format(uuid.uuid4())
    _upsert_room(safe_owner, room_id, safe_name, peers)

    return True, "created", {
        "room_id": room_id,
        "room_name": safe_name,
        "peers": peers,
        "type": "private",
    }


def get_or_create_direct_room(owner_username, peer_id):
    """Ensure one direct room exists for owner/peer pair and return room descriptor."""
    initialize_p2p_store()

    safe_owner = str(owner_username or "").strip()
    safe_peer = str(peer_id or "").strip()

    if not safe_owner or not safe_peer:
        return None

    room_id = _direct_room_id(safe_owner, safe_peer)
    _upsert_room(safe_owner, room_id, "Direct with {}".format(safe_peer), [safe_peer])

    if safe_owner != "shared":
        shared_room_id = _direct_room_id("shared", safe_peer)
        with _db_lock:
            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 1
                FROM p2p_messages
                WHERE owner_username = 'shared' AND room_id = ?
                LIMIT 1
                """,
                (shared_room_id,),
            )
            has_shared_messages = cur.fetchone() is not None

            if has_shared_messages:
                cur.execute(
                    """
                    UPDATE p2p_messages
                    SET owner_username = ?, room_id = ?, peer_id = ?
                    WHERE owner_username = 'shared' AND room_id = ?
                    """,
                    (safe_owner, room_id, safe_peer, shared_room_id),
                )
                cur.execute(
                    "DELETE FROM p2p_rooms WHERE owner_username = 'shared' AND room_id = ?",
                    (shared_room_id,),
                )
            conn.commit()
            conn.close()

    return {
        "room_id": room_id,
        "room_name": "Direct with {}".format(safe_peer),
        "peers": [safe_peer],
        "type": "direct",
    }


def get_direct_room_owners(peer_id):
    """Return owner usernames that already have direct rooms for peer."""
    initialize_p2p_store()

    safe_peer = str(peer_id or "").strip()
    if not safe_peer:
        return []

    pattern = "direct::%::{}".format(safe_peer)
    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT owner_username
            FROM p2p_rooms
            WHERE room_id LIKE ?
            ORDER BY owner_username ASC
            """,
            (pattern,),
        )
        rows = cur.fetchall()
        conn.close()

    owners = []
    for row in rows:
        owner = str(row[0] or "").strip()
        if owner:
            owners.append(owner)
    return owners


def get_room(owner_username, room_id):
    """Return one room by id for owner, or None."""
    initialize_p2p_store()

    safe_owner = str(owner_username or "").strip()
    safe_room = str(room_id or "").strip()
    if not safe_owner or not safe_room:
        return None

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT room_id, room_name, peers_json, updated_at
            FROM p2p_rooms
            WHERE owner_username = ? AND room_id = ?
            LIMIT 1
            """,
            (safe_owner, safe_room),
        )
        row = cur.fetchone()
        conn.close()

    if not row:
        return None

    return _room_row_to_dict(row)


def rename_room(owner_username, room_id, new_room_name):
    """Rename one local p2p room owned by user."""
    initialize_p2p_store()

    safe_owner = str(owner_username or "").strip()
    safe_room = str(room_id or "").strip()
    safe_name = str(new_room_name or "").strip()

    if not safe_owner:
        return False, "unauthorized"
    if not safe_room:
        return False, "invalid-room"
    if not safe_name:
        return False, "invalid-room-name"

    now = _now_iso()
    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM p2p_rooms WHERE owner_username = ? AND room_id = ?",
            (safe_owner, safe_room),
        )
        if cur.fetchone() is None:
            conn.close()
            return False, "room-not-found"

        cur.execute(
            """
            UPDATE p2p_rooms
            SET room_name = ?, updated_at = ?
            WHERE owner_username = ? AND room_id = ?
            """,
            (safe_name, now, safe_owner, safe_room),
        )
        conn.commit()
        conn.close()

    return True, safe_name


def leave_room(owner_username, room_id):
    """Delete one local room and local messages for owner."""
    initialize_p2p_store()

    safe_owner = str(owner_username or "").strip()
    safe_room = str(room_id or "").strip()

    if not safe_owner:
        return False, "unauthorized"
    if not safe_room:
        return False, "invalid-room"

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM p2p_rooms WHERE owner_username = ? AND room_id = ?",
            (safe_owner, safe_room),
        )
        if cur.fetchone() is None:
            conn.close()
            return False, "room-not-found"

        cur.execute(
            "DELETE FROM p2p_messages WHERE owner_username = ? AND room_id = ?",
            (safe_owner, safe_room),
        )
        cur.execute(
            "DELETE FROM p2p_rooms WHERE owner_username = ? AND room_id = ?",
            (safe_owner, safe_room),
        )
        conn.commit()
        conn.close()

    return True, safe_room


def add_room_message(owner_username, room_id, peer_id, sender, message, direction):
    """Store one immutable p2p/private message and update room timestamp."""
    initialize_p2p_store()

    safe_owner = str(owner_username or "").strip()
    safe_room = str(room_id or "").strip()
    safe_peer = str(peer_id or "").strip()
    safe_sender = str(sender or "").strip() or "peer"
    safe_message = str(message or "").strip()
    safe_direction = str(direction or "").strip().lower()

    if not safe_owner or not safe_room or not safe_peer or not safe_message:
        return None

    if safe_direction not in {"sent", "received"}:
        safe_direction = "received"

    now = _now_iso()
    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO p2p_messages (
                room_id,
                owner_username,
                peer_id,
                sender,
                message,
                direction,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                safe_room,
                safe_owner,
                safe_peer,
                safe_sender,
                safe_message,
                safe_direction,
                now,
            ),
        )
        cur.execute(
            """
            UPDATE p2p_rooms
            SET updated_at = ?
            WHERE room_id = ? AND owner_username = ?
            """,
            (now, safe_room, safe_owner),
        )
        conn.commit()
        conn.close()

    return {
        "room_id": safe_room,
        "peer_id": safe_peer,
        "sender": safe_sender,
        "message": safe_message,
        "direction": safe_direction,
        "timestamp": now[11:19],
    }


def get_room_messages(owner_username, room_id):
    """Return message history for one room and owner."""
    initialize_p2p_store()

    safe_owner = str(owner_username or "").strip()
    safe_room = str(room_id or "").strip()
    if not safe_owner or not safe_room:
        return []

    with _db_lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT sender, message, direction, created_at, peer_id
            FROM p2p_messages
            WHERE owner_username = ? AND room_id = ?
            ORDER BY id ASC
            """,
            (safe_owner, safe_room),
        )
        rows = cur.fetchall()
        conn.close()

    result = []
    for sender, message, direction, created_at, peer_id in rows:
        result.append(
            {
                "sender": sender,
                "message": message,
                "direction": direction,
                "peer_id": peer_id,
                "timestamp": created_at[11:19] if len(created_at) >= 19 else created_at,
            }
        )
    return result


def reset_p2p_store_runtime_state():
    """Reset in-memory initialization state to force fresh setup call."""
    global _initialized
    with _db_lock:
        _initialized = False


initialize_p2p_store()
