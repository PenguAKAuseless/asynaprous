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

import sys
import os
import importlib.util
import json

from daemon import AsynapRous
from .tracker.handlers import handle_submit_info, handle_get_list 
from .chat.handlers import handle_send_peer, handle_broadcast_peer, handle_connect_peer

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
    print("[SampleApp] Logging in {} to {}".format(headers, body))
    data = {"message": "Welcome to the RESTful TCP WebApp"}

    # Convert to JSON string
    json_str = json.dumps(data)
    return json_str.encode("utf-8")


@app.route("/echo", methods=["POST"])
def echo(headers="guest", body="anonymous"):
    print("[SampleApp] received body {}".format(body))

    try:
        message = json.loads(body)
        data = {"received": message}
        # Convert to JSON string
        json_str = json.dumps(data)
        return json_str.encode("utf-8")
    except json.JSONDecodeError:
        data = {"error": "Invalid JSON"}
        # Convert to JSON string
        json_str = json.dumps(data)
        return json_str.encode("utf-8")


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

    # Convert to JSON string
    json_str = json.dumps(data)
    return json_str.encode("utf-8")

# from tracker/handlers.py
@app.route("/submit-info", methods=["POST"])
def submit_info(headers, body):
    return handle_submit_info(headers, body)

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
    try:
        data = json.loads(body)
        sender = data.get("from", "Unknown")
        msg = data.get("msg", "")
        print(f"\n[NEW MESSAGE] from {sender}: {msg}\n")
        
        response_data = {"status": "received"}
        return json.dumps(response_data).encode("utf-8")
    except json.JSONDecodeError:
        return json.dumps({"status": "error", "message": "Invalid JSON"}).encode("utf-8")

def create_sampleapp(ip, port):
    # Prepare and launch the RESTful application
    app.prepare_address(ip, port)
    app.run()
