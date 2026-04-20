"""Chat handlers for peer messaging and channel operations."""

import json
import socket
import threading

from .channel_service import (
    add_message,
    create_channel,
    get_channels,
    get_messages,
    get_user_channels,
    join_channel,
)
from .peer_service import add_peer_info, get_all_peers, get_peer_info
from .protocol import (
    COMMAND_BROADCAST_PEER,
    COMMAND_CHANNEL_MESSAGE,
    COMMAND_SEND_PEER,
    build_envelope,
    build_error,
    validate_envelope,
)


def _json(payload):
    return json.dumps(payload)


def _parse_json(body):
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _send_http_post(target_ip, target_port, payload, endpoint="/receive-msg", timeout=5):
    """Send an HTTP POST request to target peer and return delivery result."""
    try:
        body = json.dumps(payload)
        request = (
            "POST {} HTTP/1.1\r\n"
            "Host: {}:{}\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n\r\n"
            "{}"
        ).format(endpoint, target_ip, target_port, len(body.encode("utf-8")), body)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((target_ip, int(target_port)))
        sock.sendall(request.encode("utf-8"))

        # Drain response so the peer completes write path cleanly.
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                break

        sock.close()
        return True
    except Exception as exc:
        print("[P2P Error] {}".format(exc))
        return False


def _extract_peer_payload(data):
    """Extract sender/message/channel from either envelope or legacy payload."""
    if validate_envelope(data):
        payload = data.get("payload", {})
        sender = data.get("sender", "peer")
        message = payload.get("message") or payload.get("msg", "")
        channel = payload.get("channel", "general")
        return sender, message, channel

    sender = data.get("from") or data.get("sender", "peer")
    message = data.get("msg") or data.get("message", "")
    channel = data.get("channel", "general")
    return sender, message, channel


def handle_connect_peer(headers, body):
    """Handle /connect-peer for storing remote peer endpoint."""
    _ = headers
    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    peer_id = data.get("peer_id")
    ip = data.get("ip")
    port = data.get("port")

    if not peer_id or not ip or port is None:
        return _json(build_error("missing-fields", "Missing peer_id, ip, or port"))

    if add_peer_info(peer_id, ip, port):
        return _json({"status": "connected", "peer": peer_id})

    return _json(build_error("invalid-peer", "Invalid peer endpoint"))


def handle_send_peer(headers, body):
    """Handle /send-peer direct peer-to-peer message delivery."""
    _ = headers
    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    peer_id = data.get("to_peer")
    message = str(data.get("message", "")).strip()
    sender = data.get("sender", "me")

    if not peer_id or not message:
        return _json(build_error("missing-fields", "Missing to_peer or message"))

    info = get_peer_info(peer_id)
    if not info:
        return _json(build_error("peer-not-found", "Peer not found"))

    envelope = build_envelope(
        COMMAND_SEND_PEER,
        payload={"message": message},
        sender=str(sender),
    )

    success = _send_http_post(info["ip"], info["port"], envelope, endpoint="/receive-msg")
    if success:
        return _json({"status": "sent"})

    return _json(build_error("peer-unreachable", "Peer unreachable"))


def handle_broadcast_peer(headers, body):
    """Handle /broadcast-peer for fan-out to all connected peers."""
    _ = headers
    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    message = str(data.get("message", "")).strip()
    sender = data.get("sender", "me")
    if not message:
        return _json(build_error("missing-message", "Missing message"))

    peers = get_all_peers()
    delivered = 0

    envelope = build_envelope(
        COMMAND_BROADCAST_PEER,
        payload={"message": message},
        sender=str(sender),
    )

    for info in peers.values():
        if _send_http_post(info["ip"], info["port"], envelope, endpoint="/receive-msg"):
            delivered += 1

    return _json({"status": "broadcast_done", "delivered": delivered})


def handle_receive_msg(headers, body):
    """Handle /receive-msg callback endpoint for direct peer messages."""
    _ = headers
    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    sender, message, channel = _extract_peer_payload(data)
    message = str(message).strip()
    if not message:
        return _json(build_error("empty-message", "Message is empty"))

    add_message(channel, sender, message)
    print("\n[NEW MESSAGE] from {}: {}\n".format(sender, message))
    return _json({"status": "received"})


def handle_get_channels(headers, body):
    """Handle GET /api/channels."""
    _ = headers
    _ = body
    return _json(get_channels())


def handle_get_user_channels(headers, body):
    """Handle POST /api/my-channels."""
    _ = headers
    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    user = str(data.get("user", "")).strip()
    channels = get_user_channels(user)
    return _json({"status": "ok", "channels": channels})


def handle_create_channel(headers, body):
    """Handle POST /api/create-channel."""
    _ = headers
    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "")).strip()
    user = str(data.get("user", "me")).strip()

    created, info = create_channel(channel, user)
    if info == "invalid-channel":
        return _json(build_error("invalid-channel", "Channel name is required"))

    return _json({
        "status": "created" if created else "exists",
        "channel": info,
        "user": user,
    })


def handle_join_channel(headers, body):
    """Handle POST /api/join-channel."""
    _ = headers
    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "")).strip()
    user = str(data.get("user", "me")).strip()

    ok, info = join_channel(channel, user)
    if not ok:
        if info == "channel-not-found":
            return _json(build_error("channel-not-found", "Channel does not exist"))
        return _json(build_error("invalid-channel", "Channel name is required"))

    return _json({"status": "joined", "channel": info, "user": user})


def handle_get_channel_msgs(headers, body):
    """Handle POST /api/get-messages."""
    _ = headers
    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = data.get("channel", "general")
    return _json(get_messages(channel))


def handle_send_channel_msg(headers, body):
    """Handle POST /api/send-channel and replicate to connected peers."""
    _ = headers
    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = data.get("channel", "general")
    sender = str(data.get("sender", "me"))
    message = str(data.get("message", "")).strip()

    if not message:
        return _json(build_error("missing-message", "Missing message"))
    if len(message) > 2000:
        return _json(build_error("message-too-long", "Message exceeds 2000 chars"))

    stored = add_message(channel, sender, message)

    peers = get_all_peers()
    delivered = 0
    delivered_lock = threading.Lock()

    def _send_channel(info):
        nonlocal delivered
        envelope = build_envelope(
            COMMAND_CHANNEL_MESSAGE,
            payload={"channel": channel, "message": message},
            sender=sender,
        )
        ok = _send_http_post(
            info["ip"],
            info["port"],
            envelope,
            endpoint="/api/receive-channel",
        )
        if ok:
            with delivered_lock:
                delivered += 1

    threads = []
    for info in peers.values():
        worker = threading.Thread(target=_send_channel, args=(info,), daemon=True)
        worker.start()
        threads.append(worker)

    for worker in threads:
        worker.join(timeout=2)

    return _json({"status": "ok", "delivered": delivered, "message": stored})


def handle_receive_channel_msg(headers, body):
    """Handle /api/receive-channel callback endpoint."""
    _ = headers
    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    sender, message, channel = _extract_peer_payload(data)
    message = str(message).strip()
    if not message:
        return _json(build_error("empty-message", "Message is empty"))

    add_message(channel, sender, message)
    return _json({"status": "received"})
