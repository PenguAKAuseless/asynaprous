"""Thread-safe storage for known peer endpoints."""

import threading

_connected_peers = {}
_peer_lock = threading.Lock()


def add_peer_info(peer_id, ip, port):
    """Add or update peer endpoint information."""
    if not peer_id or not ip or port is None:
        return False

    try:
        safe_port = int(port)
    except (TypeError, ValueError):
        return False

    if safe_port <= 0 or safe_port > 65535:
        return False

    with _peer_lock:
        _connected_peers[str(peer_id)] = {"ip": str(ip), "port": safe_port}
    return True


def get_peer_info(peer_id):
    """Return endpoint info for one peer id."""
    with _peer_lock:
        info = _connected_peers.get(str(peer_id))
        return dict(info) if info else None


def get_all_peers():
    """Return a copy of all connected peers."""
    with _peer_lock:
        return dict(_connected_peers)