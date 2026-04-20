"""Chat handlers for peer messaging and channel operations."""

import json
import socket
import threading
import ssl
import os

from .channel_service import (
    add_message,
    create_channel,
    get_channels,
    get_messages,
    get_user_channels,
    is_channel_member,
    leave_channel,
    join_channel,
    rename_channel,
)
from .peer_service import add_peer_info, get_all_peers, get_peer_info
from .p2p_store import (
    add_room_message,
    create_private_room,
    get_direct_room_owners,
    get_or_create_direct_room,
    get_room,
    get_room_messages,
    leave_room,
    list_rooms,
    rename_room,
)
from apps.tracker.registry import get_all_peers as get_tracker_peers
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


def _authenticated_user(headers):
    """Read authenticated username propagated by HTTP adapter."""
    if not headers:
        return ""
    return str(headers.get("X-Authenticated-User", "")).strip()


def _default_private_room_name(peers):
    """Build a readable fallback name when room_name is omitted."""
    if not isinstance(peers, list) or not peers:
        return "Private Conversation"

    cleaned = [str(peer or "").strip() for peer in peers if str(peer or "").strip()]
    if not cleaned:
        return "Private Conversation"

    if len(cleaned) <= 2:
        return "P2P: {}".format(", ".join(cleaned))

    return "P2P: {}, {} +{}".format(cleaned[0], cleaned[1], len(cleaned) - 2)


def _send_http_post(target_ip, target_port, payload, endpoint="/receive-msg", timeout=5):
    """Send an HTTP POST request to target peer and return delivery result."""
    sock = None
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

        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(timeout)

        peer_tls = os.environ.get("ASYNAPROUS_PEER_TLS", "0").strip().lower()
        use_tls = peer_tls in {"1", "true", "yes", "on"}

        sock = raw_sock
        if use_tls:
            verify = os.environ.get("ASYNAPROUS_PEER_TLS_VERIFY", "0").strip().lower()
            verify_cert = verify in {"1", "true", "yes", "on"}

            context = ssl.create_default_context()
            if verify_cert:
                ca_file = os.environ.get("ASYNAPROUS_PEER_TLS_CA_FILE", "").strip()
                if ca_file:
                    context.load_verify_locations(cafile=ca_file)
            else:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

            sock = context.wrap_socket(
                raw_sock,
                server_hostname=target_ip if verify_cert else None,
            )

        sock.connect((target_ip, int(target_port)))
        sock.sendall(request.encode("utf-8"))

        # Drain response so the peer completes write path cleanly.
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                break

        return True
    except Exception as exc:
        print("[P2P Error] {}".format(exc))
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


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
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    peer_id = data.get("to_peer")
    message = str(data.get("message", "")).strip()
    sender = auth_user

    if not peer_id or not message:
        return _json(build_error("missing-fields", "Missing to_peer or message"))

    info = get_peer_info(peer_id)
    if not info:
        return _json(build_error("peer-not-found", "Peer not found"))

    room = get_or_create_direct_room(auth_user, str(peer_id))
    if not room:
        return _json(build_error("invalid-room", "Unable to create direct room"))

    envelope = build_envelope(
        COMMAND_SEND_PEER,
        payload={
            "message": message,
            "to_peer": str(peer_id),
            "recipient_user": str(data.get("recipient_user", "shared") or "shared"),
            "room_name": room["room_name"],
        },
        sender=str(sender),
    )

    stored = add_room_message(
        auth_user,
        room["room_id"],
        str(peer_id),
        sender,
        message,
        "sent",
    )

    success = _send_http_post(info["ip"], info["port"], envelope, endpoint="/receive-msg")
    if success:
        return _json({"status": "sent", "room": room, "message": stored})

    return _json(build_error("peer-unreachable", "Peer unreachable"))


def handle_broadcast_peer(headers, body):
    """Handle /broadcast-peer for fan-out to all connected peers."""
    auth_user = _authenticated_user(headers)
    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    message = str(data.get("message", "")).strip()
    sender = auth_user or data.get("sender", "me")
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

    sender, message, _ = _extract_peer_payload(data)
    message = str(message).strip()
    if not message:
        return _json(build_error("empty-message", "Message is empty"))

    payload = data.get("payload", {}) if isinstance(data, dict) else {}
    peer_id = str(payload.get("to_peer", sender) or sender)

    target_owners = set(get_direct_room_owners(sender))
    recipient_user = str(payload.get("recipient_user", "") or "").strip()
    if recipient_user:
        target_owners.add(recipient_user)

    if not target_owners:
        target_owners.add("shared")

    for owner_username in target_owners:
        room = get_or_create_direct_room(owner_username, sender)
        if not room:
            continue

        add_room_message(
            owner_username,
            room["room_id"],
            peer_id,
            sender,
            message,
            "received",
        )

    print("\n[NEW MESSAGE] from {}: {}\n".format(sender, message))
    return _json({"status": "received"})


def handle_get_channels(headers, body):
    """Handle GET /api/channels."""
    _ = headers
    _ = body
    return _json(get_channels())


def handle_get_user_channels(headers, body):
    """Handle POST /api/my-channels."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channels = get_user_channels(auth_user)
    return _json({"status": "ok", "user": auth_user, "channels": channels})


def handle_create_channel(headers, body):
    """Handle POST /api/create-channel."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "")).strip()
    user = auth_user

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
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "")).strip()
    user = auth_user

    ok, info = join_channel(channel, user)
    if not ok:
        if info == "channel-not-found":
            return _json(build_error("channel-not-found", "Channel does not exist"))
        return _json(build_error("invalid-channel", "Channel name is required"))

    return _json({"status": "joined", "channel": info, "user": user})


def handle_join_or_create_channel(headers, body):
    """Handle POST /api/channel-upsert as merged join/create behavior."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "")).strip()
    if not channel:
        return _json(build_error("invalid-channel", "Channel name is required"))

    joined, info = join_channel(channel, auth_user)
    if joined:
        return _json({"status": "joined", "channel": info, "user": auth_user})

    if info != "channel-not-found":
        return _json(build_error("invalid-channel", "Channel name is required"))

    created, created_channel = create_channel(channel, auth_user)
    return _json(
        {
            "status": "created" if created else "joined",
            "channel": created_channel,
            "user": auth_user,
        }
    )


def handle_rename_channel(headers, body):
    """Handle POST /api/channel/rename."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "")).strip()
    new_name = str(data.get("new_name", "")).strip()

    ok, info = rename_channel(channel, new_name, auth_user)
    if not ok:
        if info == "channel-not-found":
            return _json(build_error("channel-not-found", "Channel does not exist"))
        if info == "channel-exists":
            return _json(build_error("channel-exists", "Target channel already exists"))
        if info == "forbidden":
            return _json(build_error("forbidden", "You are not a member of this channel"))
        return _json(build_error("invalid-channel", "Invalid channel name"))

    return _json({"status": "ok", "channel": info})


def handle_leave_channel(headers, body):
    """Handle POST /api/channel/leave."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "")).strip()
    ok, info = leave_channel(channel, auth_user)
    if not ok:
        if info == "channel-not-found":
            return _json(build_error("channel-not-found", "Channel does not exist"))
        if info == "not-member":
            return _json(build_error("forbidden", "You are not a member of this channel"))
        if info == "forbidden":
            return _json(build_error("forbidden", "Unauthorized"))
        return _json(build_error("invalid-channel", "Invalid channel name"))

    return _json({"status": "ok", "channel": info.get("channel", ""), "removed": True})


def handle_get_channel_msgs(headers, body):
    """Handle POST /api/get-messages."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "general")).strip() or "general"
    if not is_channel_member(channel, auth_user):
        return _json(build_error("forbidden", "You are not a member of this channel"))

    return _json(get_messages(channel))


def handle_send_channel_msg(headers, body):
    """Handle POST /api/send-channel and replicate to connected peers."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "general")).strip() or "general"
    sender = auth_user
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


def handle_get_online_peers(headers, body):
    """Handle GET /api/online-peers for peer discovery sidebar."""
    _ = body
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    known_peers = {}

    for peer_id, info in get_tracker_peers().items():
        known_peers[str(peer_id)] = {
            "peer_id": str(peer_id),
            "ip": str(info.get("ip", "")),
            "port": int(info.get("port", 0)) if info.get("port") is not None else 0,
            "source": "tracker",
        }

    for peer_id, info in get_all_peers().items():
        known_peers[str(peer_id)] = {
            "peer_id": str(peer_id),
            "ip": str(info.get("ip", "")),
            "port": int(info.get("port", 0)) if info.get("port") is not None else 0,
            "source": "direct",
        }

    peers = sorted(known_peers.values(), key=lambda item: item["peer_id"])
    return _json({"status": "ok", "peers": peers})


def handle_list_p2p_rooms(headers, body):
    """Handle POST /api/p2p/rooms for one authenticated user."""
    _ = body
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    rooms = list_rooms(auth_user)
    return _json({"status": "ok", "rooms": rooms})


def handle_create_p2p_room(headers, body):
    """Handle POST /api/p2p/create-room for local private chat rooms."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    peers = data.get("peers", [])
    room_name = str(data.get("room_name", "")).strip()
    if not room_name:
        room_name = _default_private_room_name(peers)

    ok, message, room = create_private_room(auth_user, room_name, peers)
    if not ok:
        return _json(build_error("invalid-room", message))

    return _json({"status": "created", "room": room})


def handle_get_or_create_direct_room(headers, body):
    """Handle POST /api/p2p/direct-room for one peer conversation."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    peer_id = str(data.get("peer_id", "")).strip()
    if not peer_id:
        return _json(build_error("missing-fields", "peer_id is required"))

    room = get_or_create_direct_room(auth_user, peer_id)
    if not room:
        return _json(build_error("invalid-room", "Unable to create direct room"))

    return _json({"status": "ok", "room": room})


def handle_get_p2p_messages(headers, body):
    """Handle POST /api/p2p/messages for one room's local history."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    room_id = str(data.get("room_id", "")).strip()
    if not room_id:
        return _json(build_error("invalid-room", "room_id is required"))

    room = get_room(auth_user, room_id)
    if not room:
        return _json(build_error("room-not-found", "Room not found"))

    messages = get_room_messages(auth_user, room_id)
    return _json({"status": "ok", "room": room, "messages": messages})


def handle_send_p2p_room_message(headers, body):
    """Handle POST /api/p2p/send-room and fan-out to room peers."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    room_id = str(data.get("room_id", "")).strip()
    message = str(data.get("message", "")).strip()
    recipient_user = str(data.get("recipient_user", "shared") or "shared")

    if not room_id:
        return _json(build_error("invalid-room", "room_id is required"))
    if not message:
        return _json(build_error("missing-message", "Missing message"))

    room = get_room(auth_user, room_id)
    if not room:
        return _json(build_error("room-not-found", "Room not found"))

    peers = room.get("peers", [])
    if not peers:
        return _json(build_error("invalid-room", "Room has no peers"))

    delivered = 0
    stored = []

    primary_peer = str(peers[0])
    item = add_room_message(
        auth_user,
        room_id,
        primary_peer,
        auth_user,
        message,
        "sent",
    )
    if item:
        stored.append(item)

    for peer_id in peers:
        peer_info = get_peer_info(peer_id)
        if not peer_info:
            continue

        envelope = build_envelope(
            COMMAND_SEND_PEER,
            payload={
                "message": message,
                "to_peer": peer_id,
                "recipient_user": recipient_user,
                "room_name": room.get("room_name", ""),
            },
            sender=auth_user,
        )

        if _send_http_post(peer_info["ip"], peer_info["port"], envelope, endpoint="/receive-msg"):
            delivered += 1

    return _json({"status": "ok", "room": room, "delivered": delivered, "messages": stored})


def handle_rename_p2p_room(headers, body):
    """Handle POST /api/p2p/rename for local room rename."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    room_id = str(data.get("room_id", "")).strip()
    new_name = str(data.get("new_name", "")).strip()

    ok, info = rename_room(auth_user, room_id, new_name)
    if not ok:
        if info == "room-not-found":
            return _json(build_error("room-not-found", "Room not found"))
        return _json(build_error("invalid-room", "Invalid room rename request"))

    return _json({"status": "ok", "room_id": room_id, "room_name": info})


def handle_leave_p2p_room(headers, body):
    """Handle POST /api/p2p/leave for deleting local room history."""
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    room_id = str(data.get("room_id", "")).strip()
    ok, info = leave_room(auth_user, room_id)
    if not ok:
        if info == "room-not-found":
            return _json(build_error("room-not-found", "Room not found"))
        return _json(build_error("invalid-room", "Invalid room"))

    return _json({"status": "ok", "room_id": info, "removed": True})


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
