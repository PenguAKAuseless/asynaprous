"""Channel and message storage facade backed by SQLite."""

from .message_store import (
    add_message,
    create_channel,
    get_channels,
    get_messages,
    get_user_channels,
    initialize_message_store,
    join_channel,
)


initialize_message_store()