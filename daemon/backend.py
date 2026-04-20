#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#

"""
daemon.backend
~~~~~~~~~~~~~~~~~

This module provides a backend object to manage and persist backend daemon.
It implements a basic backend server using Python's socket and threading libraries.
It supports handling multiple client connections concurrently and routing requests using a
custom HTTP adapter.

Requirements:
--------------
- socket: provide socket networking interface.
- threading: Enables concurrent client handling via threads.
- response: response utilities.
- httpadapter: the class for handling HTTP requests.
- CaseInsensitiveDict: provides dictionary for managing headers or routes.


Notes:
------
- The server create daemon threads for client handling.
- The current implementation error handling is minimal, socket errors are printed to the console.
- The actual request processing is delegated to the HttpAdapter class.

Usage Example:
--------------
>>> create_backend("127.0.0.1", 9000, routes={})

"""

import socket
import threading
import argparse
import ssl
import os

import asyncio
import inspect

from .response import *
from .httpadapter import HttpAdapter
from .dictionary import CaseInsensitiveDict

import selectors

sel = selectors.DefaultSelector()

mode_async = "callback"
# mode_async = "coroutine"
mode_async = "threading"


def _build_server_ssl_context():
    """Build optional TLS context when cert and key are configured."""
    cert_file = os.environ.get("ASYNAPROUS_TLS_CERT_FILE", "").strip()
    key_file = os.environ.get("ASYNAPROUS_TLS_KEY_FILE", "").strip()

    if not cert_file and not key_file:
        return None

    if not cert_file or not key_file:
        raise RuntimeError(
            "Both ASYNAPROUS_TLS_CERT_FILE and ASYNAPROUS_TLS_KEY_FILE are required"
        )

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if hasattr(context, "minimum_version") and hasattr(ssl, "TLSVersion"):
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    return context


def handle_client(ip, port, conn, addr, routes):
    """
    Initializes an HttpAdapter instance and delegates the client handling logic to it.

    :param ip (str): IP address of the server.
    :param port (int): Port number the server is listening on.
    :param conn (socket.socket): Client connection socket.
    :param addr (tuple): client address (IP, port).
    :param routes (dict): Dictionary of route handlers.
    """
    print("[Backend] Invoke handle_client accepted connection from {}".format(addr))
    daemon = HttpAdapter(ip, port, conn, addr, routes)

    # Handle client
    daemon.handle_client(conn, addr, routes)


# Callback for handling new client (itself run in sync mode)
def handle_client_callback(server, ip, port, conn, addr, routes):
    """
    Initialize connection instance and delegates the client handling logic to it.

    :param ip (str): IP address of the server.
    :param port (int): Port number the server is listening on.
    :param routes (dict): Dictionary of route handlers.
    """
    print(
        "[Backend] Invoke handle_client_callback accepted connection from {}".format(
            addr
        )
    )

    daemon = HttpAdapter(ip, port, conn, addr, routes)

    # Handle client
    daemon.handle_client(conn, addr, routes)


# Coroutine async/await for handling new client
async def handle_client_coroutine(reader, writer):
    """
    Coroutine in async communication to initialize connection instance
    then delegates the client handling logic to it.

    :param reader (StreamReader): Stream reader wrapper.
    :param write (Stream write): Stream write wrapper.
    """
    addr = writer.get_extra_info("peername")
    print(
        "[Backend] Invoke handle_client_coroutine accepted connection from {}".format(
            addr
        )
    )

    daemon = HttpAdapter(None, None, None, None, None)
    await daemon.handle_client_coroutine(reader, writer)


async def async_server(ip="0.0.0.0", port=7000, routes={}, ssl_context=None):
    print("[Backend] async_server **ASYNC** listening on port {}".format(port))
    if routes != {}:
        print("[Backend] route settings")
        for key, value in routes.items():
            isCoFunc = ""
            if inspect.iscoroutinefunction(value):
                isCoFunc += "**ASYNC** "
            print(
                "   + ('{}', '{}'): {}{}".format(key[0], key[1], isCoFunc, str(value))
            )

    async_server = await asyncio.start_server(
        handle_client_coroutine,
        ip,
        port,
        ssl=ssl_context,
    )
    async with async_server:
        await async_server.serve_forever()
    return


def run_backend(ip, port, routes):
    """
    Starts the backend server, binds to the specified IP and port, and listens for incoming
    connections. Each connection is handled in a separate thread. The backend accepts incoming
    connections and spawns a thread for each client.


    :param ip (str): IP address to bind the server.
    :param port (int): Port number to listen on.
    :param routes (dict): Dictionary of route handlers.
    """
    # This global variable to configure the asynchrnous mode or not
    global mode_async

    print("[Backend] run_backend with routes={}".format(routes))
    ssl_context = _build_server_ssl_context()
    if ssl_context:
        print("[Backend] TLS enabled for inbound connections")

    # Process async stream for registering the service and terminate
    if mode_async == "coroutine":
        asyncio.run(async_server(ip, port, routes, ssl_context=ssl_context))
        return

    # Process socket object
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        server.bind((ip, port))
        server.listen(50)

        print("[Backend] Listening on port {}".format(port))
        if routes != {}:
            print("[Backend] route settings")
            for key, value in routes.items():
                isCoFunc = ""
                if inspect.iscoroutinefunction(value):
                    isCoFunc += "**ASYNC** "
                print(
                    "   + ('{}', '{}'): {}{}".format(
                        key[0], key[1], isCoFunc, str(value)
                    )
                )
        
        #  TODO: implement the step of the client incomping connection
        #        using non-blocking communication
        #          + multi-thread
        #          + callback
        #          + coroutine
        #        provided handle_client routine

        if mode_async == "callback":
            # Non-blocking with callback
            server.setblocking(False)
            # Register server socket to be monitored with the selector for read events
            sel.register(
                server,
                selectors.EVENT_READ,
                (handle_client_callback, ip, port, routes),
            )
            while True:
                # Wait for events on the registered sockets
                events = sel.select(timeout=None)
                for key, _ in events:
                    callback, ip, port, routes = key.data
                    # Accept connection
                    conn, addr = key.fileobj.accept()
                    if ssl_context:
                        try:
                            conn = ssl_context.wrap_socket(conn, server_side=True)
                        except ssl.SSLError as exc:
                            print("[Backend] TLS handshake failed: {}".format(exc))
                            conn.close()
                            continue
                    # Adapter uses regular recv loop, so keep client socket blocking.
                    conn.setblocking(True)
                    # Invoke the callback to handle the client connection
                    callback(key.fileobj, ip, port, conn, addr, routes)

        else: # mode multi-thread
            while True:
                conn, addr = server.accept()
                if ssl_context:
                    try:
                        conn = ssl_context.wrap_socket(conn, server_side=True)
                    except ssl.SSLError as exc:
                        print("[Backend] TLS handshake failed: {}".format(exc))
                        conn.close()
                        continue
                # Create a thread to handle the client connection
                client_thread = threading.Thread(
                    target=handle_client, args=(ip, port, conn, addr, routes)
                )
                client_thread.daemon = True
                client_thread.start()

    except socket.error as e:
        print("Socket error: {}".format(e))


def create_backend(ip, port, routes={}):
    """
    Entry point for creating and running the backend server.

    :param ip (str): IP address to bind the server.
    :param port (int): Port number to listen on.
    :param routes (dict, optional): Dictionary of route handlers. Defaults to empty dict.
    """

    run_backend(ip, port, routes)
