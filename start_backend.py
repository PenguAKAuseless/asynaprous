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
start_backend
~~~~~~~~~~~~~~~~~

This module provides a simple entry point for deploying backend server process
using the socket framework. It parses command-line arguments to configure the
server's IP address and port, and then launches the backend server.
"""

import argparse
import ipaddress

from env_loader import load_dotenv


load_dotenv()

from daemon import create_backend

# Default port number used if none is specified via command-line arguments.
PORT = 9000

if __name__ == "__main__":
    """
    Entry point for launching the backend server.

    This block parses command-line arguments to determine the server's IP address
    and port. It then calls `create_backend(ip, port)` to start the RESTful
    application server.

    :arg --server-ip (str): IP address to bind the server (default: 127.0.0.1).
    :arg --server-port (int): Port number to bind the server (default: 9000).
    """

    parser = argparse.ArgumentParser(
        prog="Backend",
        description="Start the backend process",
        epilog="Backend daemon for http_deamon application",
    )
    parser.add_argument(
        "--server-ip",
        type=str,
        default="0.0.0.0",
        help="IP address to bind the server. Default is 0.0.0.0",
    )
    parser.add_argument(
        "--server-port",
        type=int,
        default=PORT,
        help="Port number to bind the server. Default is {}.".format(PORT),
    )
    parser.add_argument(
        "--purge-db-demo",
        action="store_true",
        help="Purge database tables and reseed demo users/channels, then exit.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive admin command such as --purge-db-demo.",
    )

    args = parser.parse_args()

    if args.purge_db_demo:
        if not args.yes:
            raise SystemExit("Refusing to purge database without --yes")

        from apps.db_admin import purge_database_to_demo

        summary = purge_database_to_demo()
        print("[start_backend] Purged demo database: {}".format(summary["db_path"]))
        print("[start_backend] Seeded accounts: {}".format(", ".join(summary["demo_accounts"])))
        print("[start_backend] Seeded channels: {}".format(", ".join(summary["channels"])))
        raise SystemExit(0)

    ip = args.server_ip
    port = args.server_port

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise SystemExit("Invalid --server-ip: {}".format(ip))

    if port <= 0 or port > 65535:
        raise SystemExit("Invalid --server-port: {}".format(port))

    print("[start_backend] Launching backend on {}:{}".format(ip, port))

    create_backend(ip, port)
