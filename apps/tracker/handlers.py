# apps/tracker/handlers.py
from .registry import register_peer, get_all_peers
import json

def handle_submit_info(headers, body):
    """Xử lý API /submit-info (POST)"""
    try:
        data = json.loads(body)
        peer_id = data.get("peer_id")
        ip = data.get("ip")
        port = data.get("port")
        
        if register_peer(peer_id, ip, port):
            return json.dumps({"status": "success", "message": "Registered"})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def handle_get_list(headers, body):
    """Xử lý API /get-list (GET)"""
    peers = get_all_peers()
    return json.dumps(peers)