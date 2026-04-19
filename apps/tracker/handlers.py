"""Tracker API handlers for peer registration and discovery."""

import json

from .registry import get_all_peers, register_peer


def _parse_json(body):
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _parse_peer_payload(body):
    data = _parse_json(body)
    if data is None:
        return None, "Invalid JSON"

    peer_id = data.get("peer_id")
    ip = data.get("ip")
    port = data.get("port")

    if not peer_id or not ip or port is None:
        return None, "Missing required fields: peer_id, ip, port"

    return data, ""


def handle_submit_info(headers, body):
    """Handle POST /submit-info for tracker peer registration."""
    _ = headers
    data, error = _parse_peer_payload(body)
    if error:
        return json.dumps({"status": "error", "message": error})

    if register_peer(data["peer_id"], data["ip"], data["port"]):
        return json.dumps({"status": "success", "message": "Registered"})

    return json.dumps({"status": "error", "message": "Invalid peer endpoint"})


def handle_add_list(headers, body):
    """Handle POST /add-list as alias of peer registration flow."""
    _ = headers
    data, error = _parse_peer_payload(body)
    if error:
        return json.dumps({"status": "error", "message": error})

    if register_peer(data["peer_id"], data["ip"], data["port"]):
        return json.dumps({"status": "success", "message": "Added"})

    return json.dumps({"status": "error", "message": "Invalid peer endpoint"})


def handle_get_list(headers, body):
    """Handle GET /get-list for tracker peer discovery."""
    _ = headers
    _ = body
    peers = get_all_peers()
    return json.dumps({"status": "success", "peers": peers})