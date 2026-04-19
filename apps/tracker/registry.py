# apps/tracker/registry.py

# { "peer_id": {"ip": "192.168.1.5", "port": 9002, "status": "online"} }
_active_peers = {}

def register_peer(peer_id, ip, port):
    _active_peers[peer_id] = {
        "ip": ip,
        "port": port,
        "last_seen": __import__('datetime').datetime.now()
    }
    return True

def get_all_peers():
    return _active_peers