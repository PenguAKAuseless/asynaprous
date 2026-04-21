"""Chat handlers for channel APIs, peer discovery, and WebRTC signaling."""

import datetime
import json
import threading
import time

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
from apps.auth.account_store import get_peer_id_for_user, get_username_for_peer_id
from .protocol import build_error


PRESENCE_TTL_SECONDS = 90

MIN_CHANNEL_LONG_POLL_SECONDS = 5
MAX_CHANNEL_LONG_POLL_SECONDS = 30
DEFAULT_CHANNEL_LONG_POLL_SECONDS = 25

MIN_SIGNAL_POLL_SECONDS = 5
MAX_SIGNAL_POLL_SECONDS = 30
DEFAULT_SIGNAL_POLL_SECONDS = 25

SIGNAL_EVENT_TTL_SECONDS = 180
MAX_SIGNAL_EVENTS_PER_PEER = 400


_presence_lock = threading.Lock()
_peer_presence = {}

_signal_lock = threading.Lock()
_signal_condition = threading.Condition(_signal_lock)
_signal_queues = {}
_signal_event_counter = 0

_channel_lock = threading.Lock()
_channel_condition = threading.Condition(_channel_lock)
_channel_versions = {}


def _now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"


def _json(payload):
    return json.dumps(payload)


def _parse_json(body):
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _safe_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum

    return parsed


def _normalize_peer_id(peer_id):
    """Normalize peer IDs for consistent comparisons and DB lookups."""
    return str(peer_id or "").strip().lower()


def _authenticated_user(headers):
    """Read authenticated username propagated by HTTP adapter."""
    if not headers:
        return ""
    return str(headers.get("X-Authenticated-User", "")).strip()


def _authenticated_peer(headers):
    """Resolve authenticated user and stable peer identifier."""
    username = _authenticated_user(headers)
    if not username:
        return "", ""

    peer_id = _normalize_peer_id(get_peer_id_for_user(username))
    return username, peer_id


def _touch_presence(username, peer_id):
    """Update in-memory presence for one authenticated peer."""
    safe_user = str(username or "").strip()
    safe_peer = _normalize_peer_id(peer_id)
    if not safe_user or not safe_peer:
        return

    with _presence_lock:
        _peer_presence[safe_peer] = {
            "user_id": safe_user,
            "last_seen": time.time(),
        }


def _collect_online_peers(exclude_peer_id=""):
    """Return online peers observed recently via authenticated requests."""
    safe_exclude = _normalize_peer_id(exclude_peer_id)
    now = time.time()
    peers = []

    with _presence_lock:
        stale_peers = []
        for peer_id, info in _peer_presence.items():
            age = now - float(info.get("last_seen", 0.0))
            if age > PRESENCE_TTL_SECONDS:
                stale_peers.append(peer_id)
                continue

            normalized_peer_id = _normalize_peer_id(peer_id)
            if normalized_peer_id == safe_exclude:
                continue

            user_id = str(info.get("user_id", "")).strip() or get_username_for_peer_id(peer_id)
            peers.append(
                {
                    "peer_id": normalized_peer_id,
                    "user_id": user_id or str(peer_id),
                    "online": True,
                }
            )

        for peer_id in stale_peers:
            _peer_presence.pop(peer_id, None)

    peers.sort(key=lambda item: (item["user_id"], item["peer_id"]))
    return peers


def _channel_version(channel_name):
    safe_channel = str(channel_name or "").strip()
    if not safe_channel:
        return 0

    with _channel_lock:
        return int(_channel_versions.get(safe_channel, 0))


def _bump_channel_version(channel_name):
    """Increase one channel's in-memory version and wake long-poll waiters."""
    safe_channel = str(channel_name or "").strip()
    if not safe_channel:
        return 0

    with _channel_condition:
        current = int(_channel_versions.get(safe_channel, 0)) + 1
        _channel_versions[safe_channel] = current
        _channel_condition.notify_all()
        return current


def _cleanup_signal_queues_locked(now_ts):
    """Drop stale signaling events and trim queue sizes."""
    for target_peer_id in list(_signal_queues.keys()):
        queue = _signal_queues.get(target_peer_id, [])
        if not queue:
            _signal_queues.pop(target_peer_id, None)
            continue

        filtered = [
            event
            for event in queue
            if now_ts - float(event.get("created_at_ts", 0.0)) <= SIGNAL_EVENT_TTL_SECONDS
        ]

        if len(filtered) > MAX_SIGNAL_EVENTS_PER_PEER:
            filtered = filtered[-MAX_SIGNAL_EVENTS_PER_PEER:]

        if filtered:
            _signal_queues[target_peer_id] = filtered
        else:
            _signal_queues.pop(target_peer_id, None)


def _collect_pending_events_locked(target_peer_id, last_event_id):
    """Return pending events for target and prune already-acknowledged records."""
    queue = _signal_queues.get(target_peer_id, [])
    if not queue:
        return []

    pending = [event for event in queue if int(event.get("event_id", 0)) > last_event_id]
    if pending:
        _signal_queues[target_peer_id] = pending
    else:
        _signal_queues.pop(target_peer_id, None)

    return list(pending)


def _queue_signal_event(signal_type, from_user, from_peer_id, to_peer_id, payload):
    """Append one signaling event to the receiver queue."""
    global _signal_event_counter

    now_ts = time.time()
    with _signal_condition:
        _cleanup_signal_queues_locked(now_ts)
        _signal_event_counter += 1

        event = {
            "event_id": _signal_event_counter,
            "type": signal_type,
            "from_user": str(from_user or ""),
            "from_peer_id": str(from_peer_id or ""),
            "to_peer_id": str(to_peer_id or ""),
            "payload": payload or {},
            "timestamp": _now_iso(),
            "created_at_ts": now_ts,
        }

        queue = _signal_queues.setdefault(str(to_peer_id), [])
        queue.append(event)
        if len(queue) > MAX_SIGNAL_EVENTS_PER_PEER:
            del queue[:-MAX_SIGNAL_EVENTS_PER_PEER]

        _signal_condition.notify_all()

    return event["event_id"]


def _sanitize_signal_event(event):
    """Return API-safe signaling event representation."""
    return {
        "event_id": int(event.get("event_id", 0)),
        "type": str(event.get("type", "")),
        "from_user": str(event.get("from_user", "")),
        "from_peer_id": str(event.get("from_peer_id", "")),
        "to_peer_id": str(event.get("to_peer_id", "")),
        "payload": event.get("payload", {}),
        "timestamp": str(event.get("timestamp", "")),
    }


def _require_authenticated_peer(headers):
    """Return authenticated identity tuple or unauthorized payload."""
    auth_user, auth_peer_id = _authenticated_peer(headers)
    if not auth_user or not auth_peer_id:
        return "", "", _json(build_error("unauthorized", "Unauthorized"))

    _touch_presence(auth_user, auth_peer_id)
    return auth_user, auth_peer_id, ""


def _read_signal_target(data, sender_peer_id):
    """Validate destination peer and sender claim for signaling payloads."""
    if not isinstance(data, dict):
        return "", _json(build_error("invalid-json", "Invalid JSON"))

    claimed_from = _normalize_peer_id(data.get("from_peer_id", ""))
    if claimed_from and claimed_from != sender_peer_id:
        return "", _json(build_error("forbidden", "Peer identity spoofing attempt"))

    to_peer_id = _normalize_peer_id(data.get("to_peer_id", data.get("to_peer", "")))
    if not to_peer_id:
        return "", _json(build_error("missing-fields", "to_peer_id is required"))

    if to_peer_id == sender_peer_id:
        return "", _json(build_error("invalid-peer", "Cannot signal yourself"))

    target_username = get_username_for_peer_id(to_peer_id)
    if not target_username:
        return "", _json(build_error("peer-not-found", "Peer not found"))

    return to_peer_id, ""


def handle_get_channels(headers, body):
    """Handle GET /api/channels."""
    _ = body
    auth_user = _authenticated_user(headers)
    if not auth_user:
        return _json(build_error("unauthorized", "Unauthorized"))

    _touch_presence(auth_user, get_peer_id_for_user(auth_user))
    return _json(get_channels())


def handle_get_user_channels(headers, body):
    """Handle POST /api/my-channels."""
    _ = body

    auth_user, peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    channels = get_user_channels(auth_user)
    return _json({"status": "ok", "user": auth_user, "peer_id": peer_id, "channels": channels})


def handle_create_channel(headers, body):
    """Handle POST /api/create-channel."""
    auth_user, _peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "")).strip()
    created, info = create_channel(channel, auth_user)
    if info == "invalid-channel":
        return _json(build_error("invalid-channel", "Channel name is required"))

    return _json(
        {
            "status": "created" if created else "exists",
            "channel": info,
            "user": auth_user,
        }
    )


def handle_join_channel(headers, body):
    """Handle POST /api/join-channel."""
    auth_user, _peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "")).strip()
    ok, info = join_channel(channel, auth_user)
    if not ok:
        if info == "channel-not-found":
            return _json(build_error("channel-not-found", "Channel does not exist"))
        return _json(build_error("invalid-channel", "Channel name is required"))

    return _json({"status": "joined", "channel": info, "user": auth_user})


def handle_join_or_create_channel(headers, body):
    """Handle POST /api/channel-upsert as merged join/create behavior."""
    auth_user, _peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

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
    auth_user, _peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

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

    _bump_channel_version(channel)
    if channel != info:
        _bump_channel_version(info)

    return _json({"status": "ok", "channel": info})


def handle_leave_channel(headers, body):
    """Handle POST /api/channel/leave."""
    auth_user, _peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

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

    _bump_channel_version(channel)
    return _json({"status": "ok", "channel": info.get("channel", ""), "removed": True})


def handle_get_channel_msgs(headers, body):
    """Handle POST /api/get-messages."""
    auth_user, _peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "general")).strip() or "general"
    if not is_channel_member(channel, auth_user):
        return _json(build_error("forbidden", "You are not a member of this channel"))

    return _json(get_messages(channel))


def handle_send_channel_msg(headers, body):
    """Handle POST /api/send-channel and persist to central channel history."""
    auth_user, _peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "general")).strip() or "general"
    message = str(data.get("message", "")).strip()

    if not is_channel_member(channel, auth_user):
        return _json(build_error("forbidden", "You are not a member of this channel"))

    if not message:
        return _json(build_error("missing-message", "Missing message"))
    if len(message) > 2000:
        return _json(build_error("message-too-long", "Message exceeds 2000 chars"))

    stored = add_message(channel, auth_user, message)
    seq = _bump_channel_version(channel)

    return _json({"status": "ok", "channel": channel, "seq": seq, "message": stored})


def handle_channel_long_poll(headers, body):
    """Handle POST /api/channel/long-poll for bounded channel updates."""
    auth_user, _peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    channel = str(data.get("channel", "general")).strip() or "general"
    if not is_channel_member(channel, auth_user):
        return _json(build_error("forbidden", "You are not a member of this channel"))

    last_seq = _safe_int(data.get("last_seq", -1), -1, -1, 10_000_000)
    timeout_seconds = _safe_int(
        data.get("timeout_seconds", DEFAULT_CHANNEL_LONG_POLL_SECONDS),
        DEFAULT_CHANNEL_LONG_POLL_SECONDS,
        MIN_CHANNEL_LONG_POLL_SECONDS,
        MAX_CHANNEL_LONG_POLL_SECONDS,
    )

    deadline = time.time() + timeout_seconds
    current_seq = _channel_version(channel)

    with _channel_condition:
        while current_seq == last_seq:
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            _channel_condition.wait(timeout=remaining)
            current_seq = int(_channel_versions.get(channel, 0))

    has_update = current_seq != last_seq
    payload = {
        "status": "ok",
        "channel": channel,
        "seq": current_seq,
        "has_update": has_update,
        "messages": get_messages(channel) if has_update else [],
    }
    return _json(payload)


def handle_get_online_peers(headers, body):
    """Handle GET /api/online-peers for signaling discovery sidebar."""
    _ = body

    auth_user, auth_peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    _touch_presence(auth_user, auth_peer_id)
    peers = _collect_online_peers(exclude_peer_id=auth_peer_id)

    return _json({"status": "ok", "peer_id": auth_peer_id, "peers": peers})


def handle_resolve_peer(headers, body):
    """Handle POST /api/peer/resolve for explicit peer-id lookups."""
    auth_user, auth_peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    _touch_presence(auth_user, auth_peer_id)

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    peer_id = _normalize_peer_id(data.get("peer_id", ""))
    if not peer_id:
        return _json(build_error("missing-fields", "peer_id is required"))

    if peer_id == auth_peer_id:
        return _json(build_error("invalid-peer", "Cannot start P2P with yourself"))

    username = get_username_for_peer_id(peer_id)
    if not username:
        return _json(build_error("peer-not-found", "Peer not found"))

    online = any(item.get("peer_id") == peer_id for item in _collect_online_peers())
    return _json(
        {
            "status": "ok",
            "peer": {
                "peer_id": peer_id,
                "user_id": username,
                "online": online,
            },
        }
    )


def handle_signal_offer(headers, body):
    """Handle POST /api/signal/offer for WebRTC offer relay."""
    auth_user, auth_peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    to_peer_id, target_error = _read_signal_target(data, auth_peer_id)
    if target_error:
        return target_error

    sdp = str(data.get("sdp", "")).strip()
    if not sdp:
        return _json(build_error("missing-fields", "sdp is required"))

    room_id = str(data.get("room_id", "")).strip()
    room_name = str(data.get("room_name", "")).strip()

    event_id = _queue_signal_event(
        "offer",
        auth_user,
        auth_peer_id,
        to_peer_id,
        {"sdp": sdp, "room_id": room_id, "room_name": room_name},
    )

    return _json({"status": "queued", "event_id": event_id, "to_peer_id": to_peer_id})


def handle_signal_answer(headers, body):
    """Handle POST /api/signal/answer for WebRTC answer relay."""
    auth_user, auth_peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    to_peer_id, target_error = _read_signal_target(data, auth_peer_id)
    if target_error:
        return target_error

    sdp = str(data.get("sdp", "")).strip()
    if not sdp:
        return _json(build_error("missing-fields", "sdp is required"))

    room_id = str(data.get("room_id", "")).strip()

    event_id = _queue_signal_event(
        "answer",
        auth_user,
        auth_peer_id,
        to_peer_id,
        {"sdp": sdp, "room_id": room_id},
    )

    return _json({"status": "queued", "event_id": event_id, "to_peer_id": to_peer_id})


def handle_signal_candidate(headers, body):
    """Handle POST /api/signal/candidate for ICE candidate relay."""
    auth_user, auth_peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    to_peer_id, target_error = _read_signal_target(data, auth_peer_id)
    if target_error:
        return target_error

    candidate = data.get("candidate")
    if candidate is None:
        return _json(build_error("missing-fields", "candidate is required"))

    payload = {
        "candidate": candidate,
        "sdp_mid": data.get("sdp_mid"),
        "sdp_mline_index": data.get("sdp_mline_index"),
        "room_id": str(data.get("room_id", "")).strip(),
    }

    event_id = _queue_signal_event(
        "candidate",
        auth_user,
        auth_peer_id,
        to_peer_id,
        payload,
    )

    return _json({"status": "queued", "event_id": event_id, "to_peer_id": to_peer_id})


def handle_signal_poll(headers, body):
    """Handle POST /api/signal/poll using bounded long polling for signaling events."""
    auth_user, auth_peer_id, unauthorized = _require_authenticated_peer(headers)
    if unauthorized:
        return unauthorized

    data = _parse_json(body)
    if data is None:
        return _json(build_error("invalid-json", "Invalid JSON"))

    claimed_peer = str(data.get("peer_id", "")).strip()
    if claimed_peer and claimed_peer != auth_peer_id:
        return _json(build_error("forbidden", "Peer identity spoofing attempt"))

    last_event_id = _safe_int(data.get("last_event_id", 0), 0, 0, 10_000_000_000)
    timeout_seconds = _safe_int(
        data.get("timeout_seconds", DEFAULT_SIGNAL_POLL_SECONDS),
        DEFAULT_SIGNAL_POLL_SECONDS,
        MIN_SIGNAL_POLL_SECONDS,
        MAX_SIGNAL_POLL_SECONDS,
    )

    deadline = time.time() + timeout_seconds
    pending = []

    with _signal_condition:
        while True:
            now_ts = time.time()
            _cleanup_signal_queues_locked(now_ts)

            pending = _collect_pending_events_locked(auth_peer_id, last_event_id)
            if pending:
                break

            remaining = deadline - now_ts
            if remaining <= 0:
                break

            _signal_condition.wait(timeout=remaining)

    events = [_sanitize_signal_event(event) for event in pending]
    new_last_event_id = last_event_id
    if events:
        new_last_event_id = max(item["event_id"] for item in events)

    peers = _collect_online_peers(exclude_peer_id=auth_peer_id)
    return _json(
        {
            "status": "ok",
            "peer_id": auth_peer_id,
            "events": events,
            "last_event_id": new_last_event_id,
            "peers": peers,
        }
    )
