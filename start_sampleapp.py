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
start_sampleapp
~~~~~~~~~~~~~~~~~

This module provides a sample RESTful web application using the AsynapRous framework.

It defines basic route handlers and launches a TCP-based backend server to serve
HTTP requests. The application includes a login endpoint and a greeting endpoint,
and can be configured via command-line arguments.
"""

import argparse
import ipaddress

from env_loader import load_dotenv


load_dotenv()

from apps import create_sampleapp

PORT = 2026  # Default port

if __name__ == "__main__":
    # Parse command-line arguments to configure server IP and port
    parser = argparse.ArgumentParser(
        prog="Backend", description="", epilog="Beckend daemon"
    )
    parser.add_argument("--server-ip", default="0.0.0.0")
    parser.add_argument("--server-port", type=int, default=PORT)

    args = parser.parse_args()
    ip = args.server_ip
    port = args.server_port

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise SystemExit("Invalid --server-ip: {}".format(ip))

    if port <= 0 or port > 65535:
        raise SystemExit("Invalid --server-port: {}".format(port))

    print("[start_sampleapp] Launching sampleapp on {}:{}".format(ip, port))

    # Prepare and launch the RESTful application
    create_sampleapp(ip, port)
