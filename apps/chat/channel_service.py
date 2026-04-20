"""Channel and message storage facade backed by SQLite."""

from .message_store import (
    add_message,
    create_channel,
    get_channels,
    get_messages,
    get_user_channels,
    initialize_message_store,
    is_channel_member,
    leave_channel,
    join_channel,
    rename_channel,
)


initialize_message_store()