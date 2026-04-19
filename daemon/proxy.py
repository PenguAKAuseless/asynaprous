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

"""Simple reverse proxy with host-based routing and round-robin support."""

import socket
import threading

RR_INDEX = {}
rr_lock = threading.Lock()


def _simple_http_response(status_line, body):
    body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    return (
        "{}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "Content-Length: {}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).format(status_line, len(body_bytes)).encode("utf-8") + body_bytes


def _read_http_message(conn, max_size=2 * 1024 * 1024):
    """Read full request bytes (headers + Content-Length body)."""
    conn.settimeout(10)
    data = b""

    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
        if len(data) > max_size:
            raise ValueError("Request too large")

    if not data:
        return b""

    header_end = data.find(b"\r\n\r\n")
    if header_end < 0:
        return data

    header_blob = data[: header_end + 4]
    body_blob = data[header_end + 4 :]

    content_length = 0
    header_text = header_blob.decode("iso-8859-1", errors="replace")
    for line in header_text.split("\r\n"):
        if line.lower().startswith("content-length:"):
            try:
                content_length = int(line.split(":", 1)[1].strip())
            except ValueError as exc:
                raise ValueError("Invalid Content-Length") from exc
            break

    while len(body_blob) < content_length:
        chunk = conn.recv(4096)
        if not chunk:
            break
        body_blob += chunk
        if len(header_blob) + len(body_blob) > max_size:
            raise ValueError("Request too large")

    if content_length > 0:
        body_blob = body_blob[:content_length]

    return header_blob + body_blob


def _extract_host(request_bytes):
    """Extract host value from HTTP headers."""
    text = request_bytes.decode("iso-8859-1", errors="replace")
    for line in text.split("\r\n"):
        if line.lower().startswith("host:"):
            return line.split(":", 1)[1].strip()
    return None


def forward_request(host, port, request_bytes):
    """Forward request to backend and return raw response bytes."""
    backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    backend.settimeout(10)

    try:
        backend.connect((host, int(port)))
        backend.sendall(request_bytes)

        response = b""
        while True:
            chunk = backend.recv(4096)
            if not chunk:
                break
            response += chunk

        return response
    except socket.error as exc:
        print("[Proxy] Forwarding error: {}".format(exc))
        return _simple_http_response("HTTP/1.1 502 Bad Gateway", "502 Bad Gateway")
    finally:
        backend.close()


def resolve_routing_policy(hostname, routes):
    """Resolve backend from host mapping and configured distribution policy."""
    if not hostname:
        return None, None

    route_data = routes.get(hostname)
    if route_data is None and ":" in hostname:
        route_data = routes.get(hostname.split(":", 1)[0])

    if route_data is None:
        return None, None

    proxy_map, policy = route_data
    candidates = list(proxy_map) if isinstance(proxy_map, list) else [proxy_map]
    if not candidates:
        return None, None

    if len(candidates) == 1:
        target = candidates[0]
    else:
        strategy = (policy or "round-robin").strip().lower()
        if strategy != "round-robin":
            strategy = "round-robin"

        with rr_lock:
            idx = RR_INDEX.get(hostname, 0) % len(candidates)
            target = candidates[idx]
            RR_INDEX[hostname] = RR_INDEX.get(hostname, 0) + 1

    if ":" not in target:
        return None, None

    target_host, target_port = target.rsplit(":", 1)
    return target_host.strip(), target_port.strip()


def handle_client(ip, port, conn, addr, routes):
    """Handle one proxy client request and forward to selected backend."""
    _ = ip
    _ = port

    try:
        request_bytes = _read_http_message(conn)
        if not request_bytes:
            return

        hostname = _extract_host(request_bytes)
        if not hostname:
            conn.sendall(_simple_http_response("HTTP/1.1 400 Bad Request", "Missing Host header"))
            return

        resolved_host, resolved_port = resolve_routing_policy(hostname, routes)
        if not resolved_host:
            conn.sendall(_simple_http_response("HTTP/1.1 404 Not Found", "Host not mapped"))
            return

        print(
            "[Proxy] {} Host {} -> {}:{}".format(
                addr, hostname, resolved_host, resolved_port
            )
        )

        response = forward_request(resolved_host, resolved_port, request_bytes)
        conn.sendall(response)

    except ValueError as exc:
        conn.sendall(_simple_http_response("HTTP/1.1 400 Bad Request", str(exc)))
    except Exception as exc:
        print("[Proxy] Client handling error: {}".format(exc))
        conn.sendall(_simple_http_response("HTTP/1.1 500 Internal Server Error", "Proxy error"))
    finally:
        conn.close()


def run_proxy(ip, port, routes):
    """Start proxy process and fan-out accepted sockets using threads."""
    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        proxy.bind((ip, port))
        proxy.listen(50)
        print("[Proxy] Listening on IP {} port {}".format(ip, port))

        while True:
            conn, addr = proxy.accept()
            client_thread = threading.Thread(
                target=handle_client,
                args=(ip, port, conn, addr, routes),
                daemon=True,
            )
            client_thread.start()

    except socket.error as exc:
        print("Socket error: {}".format(exc))
    finally:
        proxy.close()


def create_proxy(ip, port, routes):
    """Entry point for launching the proxy server."""
    run_proxy(ip, port, routes)
