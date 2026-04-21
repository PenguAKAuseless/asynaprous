"""Database admin commands for development and demo workflows."""

import sqlite3

from .auth.account_store import (
    get_db_path,
    get_demo_account_rows,
    initialize_account_store,
    reset_account_store_runtime_state,
)
from .auth.session_store import reset_session_store_runtime_state
from .chat.message_store import (
    get_channels,
    initialize_message_store,
    reset_message_store_runtime_state,
)
from .chat.peer_service import reset_peer_store_runtime_state


def purge_database_to_demo():
    """Drop runtime data tables and reseed demo accounts/channels."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    cur = conn.cursor()

    cur.execute("PRAGMA foreign_keys = OFF")
    cur.execute("DROP TABLE IF EXISTS channel_members")
    cur.execute("DROP TABLE IF EXISTS messages")
    cur.execute("DROP TABLE IF EXISTS channels")
    cur.execute("DROP TABLE IF EXISTS accounts")
    cur.execute("DROP TABLE IF EXISTS auth_sessions")
    cur.execute("DROP TABLE IF EXISTS p2p_messages")
    cur.execute("DROP TABLE IF EXISTS p2p_rooms")
    cur.execute("DROP TABLE IF EXISTS known_peers")

    conn.commit()
    conn.close()

    reset_account_store_runtime_state()
    reset_message_store_runtime_state()
    reset_session_store_runtime_state()
    reset_peer_store_runtime_state()

    initialize_account_store()
    initialize_message_store()

    return {
        "db_path": db_path,
        "demo_accounts": [row["username"] for row in get_demo_account_rows()],
        "channels": get_channels(),
    }
