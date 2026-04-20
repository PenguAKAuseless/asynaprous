#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course,
# and is released under the "MIT License Agreement". Please see the LICENSE
# file that should have been included as part of this package.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#


"""
app.sampleapp
~~~~~~~~~~~~~~~~~

"""

import json
from urllib.parse import parse_qs

from daemon import AsynapRous
from .auth.account_store import create_account
from .tracker.handlers import handle_add_list, handle_get_list, handle_submit_info
from .chat.handlers import (
    handle_broadcast_peer,
    handle_create_p2p_room,
    handle_connect_peer,
    handle_create_channel,
    handle_get_channel_msgs,
    handle_get_or_create_direct_room,
    handle_get_channels,
    handle_get_online_peers,
    handle_get_p2p_messages,
    handle_get_user_channels,
    handle_join_or_create_channel,
    handle_join_channel,
    handle_leave_channel,
    handle_leave_p2p_room,
    handle_list_p2p_rooms,
    handle_rename_channel,
    handle_rename_p2p_room,
    handle_receive_channel_msg,
    handle_receive_msg,
    handle_send_channel_msg,
    handle_send_p2p_room_message,
    handle_send_peer,
)

app = AsynapRous()


@app.route("/login", methods=["POST"])
def login(headers="guest", body="anonymous"):
    """
    Handle user login via POST request.

    This route simulates a login process and prints the provided headers and body
    to the console.

    :param headers (str): The request headers or user identifier.
    :param body (str): The request body or login payload.
    """
    username = "anonymous"
    content_type = headers.get("Content-Type", "") if headers else ""

    if "application/json" in content_type:
        try:
            payload = json.loads(body)
            username = payload.get("username") or payload.get("user") or username
        except (TypeError, json.JSONDecodeError):
            pass
    elif "application/x-www-form-urlencoded" in content_type:
        form = parse_qs(body, keep_blank_values=True)
        username = form.get("username", [username])[0]

    print("[SampleApp] Login request for user '{}'".format(username))

    data = {
        "status": "ok",
        "message": "Welcome to the RESTful TCP WebApp",
        "user": username,
    }
    return json.dumps(data)


@app.route("/register", methods=["POST"])
def register(headers="guest", body=""):
    """Handle user self-registration with confirm password check."""
    content_type = headers.get("Content-Type", "") if headers else ""
    username = ""
    password = ""
    confirm_password = ""

    if "application/json" in content_type:
        try:
            payload = json.loads(body)
        except (TypeError, json.JSONDecodeError):
            return json.dumps({"status": "error", "message": "Invalid JSON"})

        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        confirm_password = str(payload.get("confirm_password", ""))
    elif "application/x-www-form-urlencoded" in content_type:
        form = parse_qs(body, keep_blank_values=True)
        username = str(form.get("username", [""])[0]).strip()
        password = str(form.get("password", [""])[0])
        confirm_password = str(form.get("confirm_password", [""])[0])
    else:
        return json.dumps({"status": "error", "message": "Unsupported content type"})

    if password != confirm_password:
        return json.dumps({"status": "error", "message": "Passwords do not match"})

    created, message = create_account(username, password)
    if not created:
        return json.dumps({"status": "error", "message": message})

    return json.dumps({"status": "ok", "message": "Account created"})


@app.route("/echo", methods=["POST"])
def echo(headers="guest", body="anonymous"):
    print("[SampleApp] received body {}".format(body))

    try:
        message = json.loads(body)
        data = {"received": message}
        return json.dumps(data)
    except json.JSONDecodeError:
        data = {"error": "Invalid JSON"}
        return json.dumps(data)


@app.route("/hello", methods=["PUT"])
async def hello(headers, body):
    """
    Handle greeting via PUT request.

    This route prints a greeting message to the console using the provided headers
    and body.

    :param headers (str): The request headers or user identifier.
    :param body (str): The request body or message payload.
    """
    print("[SampleApp] ['PUT'] **ASYNC** Hello in {} to {}".format(headers, body))
    data = {"id": 1, "name": "Alice", "email": "alice@example.com"}

    return json.dumps(data)

# from tracker/handlers.py
@app.route("/submit-info", methods=["POST"])
def submit_info(headers, body):
    return handle_submit_info(headers, body)


@app.route("/add-list", methods=["POST"])
def add_list(headers, body):
    return handle_add_list(headers, body)

@app.route("/get-list", methods=["GET"])
def get_list(headers, body):
    return handle_get_list(headers, body)

# from chat/handlers.py
@app.route("/send-peer", methods=["POST"])
def send_peer(headers, body):
    return handle_send_peer(headers, body)

@app.route("/broadcast-peer", methods=["POST"])
def broadcast_peer(headers, body):
    return handle_broadcast_peer(headers, body)

@app.route("/connect-peer", methods=["POST"])
def connect_peer(headers, body):
    return handle_connect_peer(headers, body)

@app.route("/receive-msg", methods=["POST"])
def receive_msg(headers, body):
    return handle_receive_msg(headers, body)

@app.route("/api/channels", methods=["GET"])
def api_channels(headers, body):
    return handle_get_channels(headers, body)


@app.route("/api/my-channels", methods=["POST"])
def api_my_channels(headers, body):
    return handle_get_user_channels(headers, body)


@app.route("/api/create-channel", methods=["POST"])
def api_create_channel(headers, body):
    return handle_create_channel(headers, body)


@app.route("/api/join-channel", methods=["POST"])
def api_join_channel(headers, body):
    return handle_join_channel(headers, body)


@app.route("/api/channel-upsert", methods=["POST"])
def api_channel_upsert(headers, body):
    return handle_join_or_create_channel(headers, body)


@app.route("/api/channel/rename", methods=["POST"])
def api_channel_rename(headers, body):
    return handle_rename_channel(headers, body)


@app.route("/api/channel/leave", methods=["POST"])
def api_channel_leave(headers, body):
    return handle_leave_channel(headers, body)

@app.route("/api/get-messages", methods=["POST"])
def api_get_messages(headers, body):
    return handle_get_channel_msgs(headers, body)

@app.route("/api/send-channel", methods=["POST"])
def api_send_channel(headers, body):
    return handle_send_channel_msg(headers, body)

@app.route("/api/receive-channel", methods=["POST"])
def api_receive_channel(headers, body):
    return handle_receive_channel_msg(headers, body)


@app.route("/api/online-peers", methods=["GET"])
def api_online_peers(headers, body):
    return handle_get_online_peers(headers, body)


@app.route("/api/p2p/rooms", methods=["POST"])
def api_p2p_rooms(headers, body):
    return handle_list_p2p_rooms(headers, body)


@app.route("/api/p2p/create-room", methods=["POST"])
def api_p2p_create_room(headers, body):
    return handle_create_p2p_room(headers, body)


@app.route("/api/p2p/direct-room", methods=["POST"])
def api_p2p_direct_room(headers, body):
    return handle_get_or_create_direct_room(headers, body)


@app.route("/api/p2p/messages", methods=["POST"])
def api_p2p_messages(headers, body):
    return handle_get_p2p_messages(headers, body)


@app.route("/api/p2p/send-room", methods=["POST"])
def api_p2p_send_room(headers, body):
    return handle_send_p2p_room_message(headers, body)


@app.route("/api/p2p/rename", methods=["POST"])
def api_p2p_rename(headers, body):
    return handle_rename_p2p_room(headers, body)


@app.route("/api/p2p/leave", methods=["POST"])
def api_p2p_leave(headers, body):
    return handle_leave_p2p_room(headers, body)

def create_sampleapp(ip, port):
    # Prepare and launch the RESTful application
    app.prepare_address(ip, port)
    app.run()
