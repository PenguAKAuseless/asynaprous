"""Tracker registry for active peers."""

import datetime
import threading

# {"peer_id": {"ip": str, "port": int, "last_seen": iso8601}}
_active_peers = {}
_peer_lock = threading.Lock()


def register_peer(peer_id, ip, port):
    """Register or update a peer endpoint."""
    if not peer_id or not ip or port is None:
        return False

    try:
        safe_port = int(port)
    except (TypeError, ValueError):
        return False

    if safe_port <= 0 or safe_port > 65535:
        return False

    with _peer_lock:
        _active_peers[str(peer_id)] = {
            "ip": str(ip),
            "port": safe_port,
            "last_seen": datetime.datetime.utcnow().isoformat() + "Z",
        }
    return True


def get_all_peers():
    """Return a shallow copy of all tracked peers."""
    with _peer_lock:
        return dict(_active_peers)