# apps/chat/channel_service.py
import datetime

# { "channel_name": [ {"sender": "...", "message": "...", "timestamp": "..."} ] }
_channels = {
    "general": [],
    "networking": [],
    "random": []
}

def get_channels():
    return list(_channels.keys())

def get_messages(channel_name):
    return _channels.get(channel_name, [])

def add_message(channel_name, sender, message):
    if channel_name not in _channels:
        _channels[channel_name] = []
        
    msg_obj = {
        "sender": sender,
        "message": message,
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
    }
    _channels[channel_name].append(msg_obj)
    return msg_obj