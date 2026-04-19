import json
import socket
from .peer_service import add_peer_info, get_all_peers, get_peer_info
from .channel_service import get_channels, get_messages, add_message

def _send_http_post(target_ip, target_port, payload):
    """
    Send an HTTP POST request t  o the target peer with the given payload.
    This function creates a raw socket connection to the target peer and sends
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   # create new socket
        s.settimeout(5)
        s.connect((target_ip, target_port))                     # connect to target peer
        
        body = json.dumps(payload)
        request = (
            f"POST /receive-msg HTTP/1.1\r\n"
            f"Host: {target_ip}:{target_port}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
            f"{body}"
        )
        s.sendall(request.encode('utf-8'))
        s.close()
        return True
    except Exception as e:
        print(f"[P2P Error] {e}")
        return False

def handle_connect_peer(headers, body):
    """
    Handle the connection request from another peer.
    """
    data = json.loads(body)
    peer_id = data.get("peer_id")
    ip = data.get("ip")
    port = data.get("port")
    if add_peer_info(peer_id, ip, port):        # from peer_service.py - Save info 
        return json.dumps({"status": "connected", "peer": peer_id})
    return json.dumps({"status": "error"})

def handle_send_peer(headers, body):
    """
    API /send-peer: direct message to a specific peer (to_peer) 
    """
    data = json.loads(body)
    peer_id = data.get("to_peer")   
    message = data.get("message")
    
    info = get_peer_info(peer_id)
    if info:
        # Send message to the target peer using HTTP POST
        success = _send_http_post(info['ip'], info['port'], {"from": "me", "msg": message})
        if success:
            return json.dumps({"status": "sent"})
    return json.dumps({"status": "error", "message": "Peer unreachable"})

def handle_broadcast_peer(headers, body):
    """
    API /broadcast-peer: Send message to all peers in the chat list
    """
    data = json.loads(body)
    message = data.get("message")
    peers = get_all_peers()
    count = 0
    for p_id, info in peers.items():
        if _send_http_post(info['ip'], info['port'], {"from": "me", "msg": message}):
            count += 1
    return json.dumps({"status": "broadcast_done", "delivered": count})

# You can add more handlers for channel management, message retrieval, etc. here.
def handle_get_channels(headers, body):
    return json.dumps(get_channels())

def handle_get_channel_msgs(headers, body):
    data = json.loads(body)
    channel = data.get("channel", "general")
    return json.dumps(get_messages(channel))

def handle_send_channel_msg(headers, body):
    data = json.loads(body)
    channel = data.get("channel", "general")
    msg = data.get("message", "")
    sender = data.get("sender", "me")
    
    add_message(channel, sender, msg)
    return json.dumps({"status": "ok"})