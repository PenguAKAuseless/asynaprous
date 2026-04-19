"""Protocol envelope helpers for peer-to-peer and channel messaging."""

import time

PROTOCOL_VERSION = "1.0"

COMMAND_CONNECT_PEER = "connect-peer"
COMMAND_SEND_PEER = "send-peer"
COMMAND_BROADCAST_PEER = "broadcast-peer"
COMMAND_CHANNEL_MESSAGE = "channel-message"

KNOWN_COMMANDS = {
    COMMAND_CONNECT_PEER,
    COMMAND_SEND_PEER,
    COMMAND_BROADCAST_PEER,
    COMMAND_CHANNEL_MESSAGE,
}


def build_envelope(command, payload=None, sender="system"):
    """Build normalized protocol envelope."""
    return {
        "version": PROTOCOL_VERSION,
        "command": command,
        "sender": sender,
        "timestamp": int(time.time()),
        "payload": payload or {},
    }


def build_error(code, message):
    """Build normalized error payload."""
    return {"status": "error", "error": {"code": code, "message": message}}


def validate_envelope(message):
    """Validate received envelope shape."""
    if not isinstance(message, dict):
        return False

    version = message.get("version")
    command = message.get("command")
    payload = message.get("payload")

    if version != PROTOCOL_VERSION:
        return False
    if command not in KNOWN_COMMANDS:
        return False
    if payload is None or not isinstance(payload, dict):
        return False

    return True
