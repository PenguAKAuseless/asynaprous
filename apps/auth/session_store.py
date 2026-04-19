import threading
import time
import uuid

SESSION_TTL_SECONDS = 3600

# {"session_id": {"username": str, "expires_at": float}}
_sessions = {}
_sessions_lock = threading.Lock()


def create_session(username, ttl_seconds=SESSION_TTL_SECONDS):
    """Create a new session and return generated session id."""
    session_id = str(uuid.uuid4())
    expires_at = time.time() + int(ttl_seconds)

    with _sessions_lock:
        _sessions[session_id] = {
            "username": str(username),
            "expires_at": expires_at,
        }

    return session_id


def get_session_user(session_id):
    """Return username for valid session, otherwise None."""
    if not session_id:
        return None

    now = time.time()
    with _sessions_lock:
        data = _sessions.get(session_id)
        if not data:
            return None

        if data.get("expires_at", 0) <= now:
            _sessions.pop(session_id, None)
            return None

        return data.get("username")


def remove_session(session_id):
    """Delete session id from storage."""
    if not session_id:
        return False

    with _sessions_lock:
        return _sessions.pop(session_id, None) is not None


def cleanup_expired_sessions():
    """Remove all expired sessions and return removed count."""
    now = time.time()
    removed = 0

    with _sessions_lock:
        expired_ids = [
            sid for sid, data in _sessions.items() if data.get("expires_at", 0) <= now
        ]
        for sid in expired_ids:
            _sessions.pop(sid, None)
            removed += 1

    return removed