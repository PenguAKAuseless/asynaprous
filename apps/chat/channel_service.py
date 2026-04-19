"""Thread-safe in-memory channel and message storage."""

import datetime
import threading

_channels = {
    "general": [],
    "networking": [],
    "random": [],
}
_channel_lock = threading.Lock()


def get_channels():
    """Return available channel names."""
    with _channel_lock:
        return list(_channels.keys())


def get_messages(channel_name):
    """Return a copy of messages for one channel."""
    safe_channel = str(channel_name or "general")
    with _channel_lock:
        messages = _channels.get(safe_channel, [])
        return [dict(item) for item in messages]


def add_message(channel_name, sender, message):
    """Append immutable message object to channel history."""
    safe_channel = str(channel_name or "general")
    safe_sender = str(sender or "anonymous")
    safe_message = str(message or "")

    with _channel_lock:
        if safe_channel not in _channels:
            _channels[safe_channel] = []

        msg_obj = {
            "sender": safe_sender,
            "message": safe_message,
            "timestamp": datetime.datetime.utcnow().strftime("%H:%M:%S"),
        }
        _channels[safe_channel].append(msg_obj)

    return dict(msg_obj)