# apps/chat/peer_service.py

# { "peer_id": socket_connection }
# _connected_peers = {}

# def add_connection(peer_id, connection):
#     _connected_peers[peer_id] = connection
#     return True

# def get_all_connections():
#     return _connected_peers

# -- 
# Lưu trữ thông tin logic: { "peer_id": {"ip": "...", "port": ...} } - Không lưu connection  - vì khi http conc đóng thì chết.

_connected_peers = {}

def add_peer_info(peer_id, ip, port):
    _connected_peers[peer_id] = {"ip": ip, "port": int(port)}
    return True

def get_peer_info(peer_id):
    return _connected_peers.get(peer_id)

def get_all_peers():
    return _connected_peers