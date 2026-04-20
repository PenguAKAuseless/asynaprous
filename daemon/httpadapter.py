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
daemon.httpadapter
~~~~~~~~~~~~~~~~~

This module provides an HTTP adapter object to manage request parsing,
authentication checks, route dispatch, and response delivery.
"""

import asyncio
import inspect
import json
import os

from .request import Request
from .response import Response
from apps.auth.handlers import check_credentials
from apps.auth.session_store import (
    SESSION_TTL_SECONDS,
    create_session,
    get_session_user,
    remove_session,
)


class HttpAdapter:
    """HTTP adapter for managing client connections and routing."""

    __attrs__ = [
        "ip",
        "port",
        "conn",
        "connaddr",
        "routes",
        "request",
        "response",
    ]

    def __init__(self, ip, port, conn, connaddr, routes):
        self.ip = ip
        self.port = port
        self.conn = conn
        self.connaddr = connaddr
        self.routes = routes or {}
        self.request = Request()
        self.response = Response()

    def _read_http_message(self, conn, max_size=2 * 1024 * 1024):
        """Read full HTTP request headers and body using Content-Length."""
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
            return ""

        header_end = data.find(b"\r\n\r\n")
        if header_end < 0:
            return data.decode("utf-8", errors="replace")

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

        full_request = header_blob + body_blob
        return full_request.decode("utf-8", errors="replace")

    async def _read_http_message_async(self, reader, max_size=2 * 1024 * 1024):
        """Async variant for reading an HTTP request."""
        data = b""

        while b"\r\n\r\n" not in data:
            chunk = await reader.read(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > max_size:
                raise ValueError("Request too large")

        if not data:
            return ""

        header_end = data.find(b"\r\n\r\n")
        if header_end < 0:
            return data.decode("utf-8", errors="replace")

        header_blob = data[: header_end + 4]
        body_blob = data[header_end + 4 :]

        content_length = 0
        header_text = header_blob.decode("iso-8859-1", errors="replace")
        for line in header_text.split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
                break

        while len(body_blob) < content_length:
            chunk = await reader.read(4096)
            if not chunk:
                break
            body_blob += chunk
            if len(header_blob) + len(body_blob) > max_size:
                raise ValueError("Request too large")

        if content_length > 0:
            body_blob = body_blob[:content_length]

        full_request = header_blob + body_blob
        return full_request.decode("utf-8", errors="replace")

    def _is_public_path(self, path):
        """Return True for paths that do not require authentication."""
        if path in {
            "/",
            "/index.html",
            "/login",
            "/login.html",
            "/form.html",
            "/echo",
            "/chat.html",
            "/receive-msg",
            "/api/receive-channel",
            "/favicon.ico",
        }:
            return True

        return path.startswith("/css/") or path.startswith("/js/") or path.startswith(
            "/images/"
        )

    def _is_protected_path(self, path):
        """Return True for endpoints requiring valid session or valid auth header."""
        if self._is_public_path(path):
            return False

        if path in {
            "/submit-info",
            "/add-list",
            "/get-list",
            "/connect-peer",
            "/broadcast-peer",
            "/send-peer",
            "/hello",
            "/logout",
        }:
            return True

        return path.startswith("/api/")

    def _build_internal_error(self, message="Internal Server Error"):
        body = message.encode("utf-8")
        response = (
            "HTTP/1.1 500 Internal Server Error\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).format(len(body)).encode("utf-8")
        return response + body

    def _connection_uses_tls(self):
        """Best-effort check for TLS-wrapped connection in sync mode."""
        conn = self.conn
        if not conn:
            return False

        if hasattr(conn, "cipher"):
            try:
                return conn.cipher() is not None
            except Exception:
                return False

        return False

    def _should_set_secure_cookie(self, req):
        """Determine whether session cookies should include the Secure attribute."""
        mode = os.environ.get("ASYNAPROUS_COOKIE_SECURE", "auto").strip().lower()
        if mode in {"1", "true", "yes", "on"}:
            return True
        if mode in {"0", "false", "no", "off"}:
            return False

        if req and req.headers:
            forwarded_proto = str(req.headers.get("X-Forwarded-Proto", "")).strip()
            if forwarded_proto:
                first_proto = forwarded_proto.split(",", 1)[0].strip().lower()
                if first_proto == "https":
                    return True

            forwarded = str(req.headers.get("Forwarded", "")).lower()
            if "proto=https" in forwarded:
                return True

        return self._connection_uses_tls()

    def _set_session_cookie(self, req, session_id, max_age):
        """Set session cookie with secure attributes based on transport policy."""
        self.response.set_cookie(
            "session_id",
            session_id,
            max_age=max_age,
            path="/",
            secure=self._should_set_secure_cookie(req),
        )

    def _invoke_hook(self, req):
        """Run route hook for sync and async handlers."""
        kwargs = {"headers": req.headers, "body": req.body}

        if inspect.iscoroutinefunction(req.hook):
            return asyncio.run(req.hook(**kwargs))
        return req.hook(**kwargs)

    def _credentials_from_request(self, req):
        """Extract credentials from body first, then fallback to Authorization."""
        body_creds = req.extract_credentials_from_body()
        if body_creds:
            return body_creds

        if isinstance(req.auth, tuple) and len(req.auth) == 2:
            return req.auth

        return None

    def _attach_authenticated_user(self, req, username):
        """Attach authenticated user to request headers for route handlers."""
        if not req or not username:
            return

        req.headers["X-Authenticated-User"] = str(username)

    def _authenticate_request(self, req):
        """Validate session cookie or basic credentials for protected endpoints."""
        session_id = req.cookies.get("session_id") if req.cookies else None
        user_from_session = get_session_user(session_id)
        if user_from_session:
            self._attach_authenticated_user(req, user_from_session)
            return user_from_session

        if isinstance(req.auth, tuple) and check_credentials(req.auth):
            if not self._connection_uses_tls():
                warn = os.environ.get("ASYNAPROUS_WARN_INSECURE_AUTH", "1").strip().lower()
                if warn not in {"0", "false", "no", "off"}:
                    print(
                        "[Security] Basic auth accepted on non-TLS connection; credentials can be intercepted"
                    )
            username = req.auth[0]
            session_id = create_session(username)
            self._set_session_cookie(req, session_id, SESSION_TTL_SECONDS)
            self._attach_authenticated_user(req, username)
            return username

        return None

    def _handle_login(self, req):
        """Process login with body/auth credentials and set session cookie."""
        credentials = self._credentials_from_request(req)
        if not credentials or not check_credentials(credentials):
            return self.response.build_unauthorized()

        username = credentials[0]
        session_id = create_session(username)
        self._set_session_cookie(req, session_id, SESSION_TTL_SECONDS)
        self.response.headers["Cache-Control"] = "no-store"

        if req.hook:
            content = self._invoke_hook(req)
        else:
            content = json.dumps({"status": "ok", "message": "Login successful"})

        return self.response.build_response(req, envelop_content=content)

    def _handle_logout(self, req):
        """Clear session state and instruct browser to remove cookie."""
        session_id = req.cookies.get("session_id") if req.cookies else None
        if session_id:
            remove_session(session_id)

        self.response.set_cookie(
            "session_id",
            "deleted",
            max_age=0,
            path="/",
            secure=self._should_set_secure_cookie(req),
        )
        self.response.headers["Cache-Control"] = "no-store"
        content = json.dumps({"status": "ok", "message": "Logged out"})
        return self.response.build_response(req, envelop_content=content)

    def handle_client(self, conn, addr, routes):
        """Handle an incoming client request in blocking mode."""
        self.conn = conn
        self.connaddr = addr
        self.routes = routes or {}

        req = self.request
        resp = self.response

        try:
            msg = self._read_http_message(conn)
            if not msg:
                return

            req.prepare(msg, self.routes)
            if not req.is_valid:
                response = resp.build_bad_request(req.error or "400 Bad Request")
                conn.sendall(response)
                return

            req.prepare_auth(req.headers.get("Authorization"))

            if req.path == "/login" and req.method == "POST":
                response = self._handle_login(req)
                conn.sendall(response)
                return

            if req.path == "/logout" and req.method in {"GET", "POST"}:
                response = self._handle_logout(req)
                conn.sendall(response)
                return

            if self._is_protected_path(req.path):
                user = self._authenticate_request(req)
                if not user:
                    response = resp.build_unauthorized()
                    conn.sendall(response)
                    return

            if req.hook:
                content = self._invoke_hook(req)
                response = resp.build_response(req, envelop_content=content)
            else:
                response = resp.build_response(req)

            conn.sendall(response)

        except ValueError as exc:
            conn.sendall(resp.build_bad_request(str(exc)))
        except Exception:
            conn.sendall(self._build_internal_error())
        finally:
            conn.close()

    async def handle_client_coroutine(self, reader, writer):
        """Handle an incoming client request in async mode."""
        req = self.request
        resp = self.response

        try:
            msg = await self._read_http_message_async(reader)
            if not msg:
                writer.close()
                await writer.wait_closed()
                return

            req.prepare(msg, routes=self.routes)
            if not req.is_valid:
                writer.write(resp.build_bad_request(req.error or "400 Bad Request"))
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            req.prepare_auth(req.headers.get("Authorization"))

            if req.path == "/login" and req.method == "POST":
                writer.write(self._handle_login(req))
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            if req.path == "/logout" and req.method in {"GET", "POST"}:
                writer.write(self._handle_logout(req))
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            if self._is_protected_path(req.path):
                user = self._authenticate_request(req)
                if not user:
                    writer.write(resp.build_unauthorized())
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()
                    return

            if req.hook:
                if inspect.iscoroutinefunction(req.hook):
                    content = await req.hook(headers=req.headers, body=req.body)
                else:
                    content = req.hook(headers=req.headers, body=req.body)
                writer.write(resp.build_response(req, envelop_content=content))
            else:
                writer.write(resp.build_response(req))

            await writer.drain()

        except Exception:
            writer.write(self._build_internal_error())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    def add_headers(self, request):
        """Override point for custom request headers."""
        _ = request

    def build_proxy_headers(self, proxy):
        """Build extra headers for requests forwarded through proxy."""
        _ = proxy
        return {}
