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
daemon.request
~~~~~~~~~~~~~~~~~

This module provides a Request object to manage and persist request settings,
including request line parsing, header/body extraction, cookies, and
authentication metadata.
"""

import base64
import json
from urllib.parse import parse_qs, urlsplit

from .dictionary import CaseInsensitiveDict


class Request:
    """The fully mutable "class" `Request <Request>` object,
    containing the exact bytes that will be sent to the server.

    Instances are generated from a "class" `Request <Request>` object, and
    should not be instantiated manually; doing so may produce undesirable
    effects.

    Usage::

      >>> import deamon.request
      >>> req = request.Request()
      ## Incoming message obtain aka. incoming_msg
      >>> r = req.prepare(incoming_msg)
      >>> r
      <Request>
    """

    __attrs__ = [
        "method",
        "path",
        "version",
        "url",
        "headers",
        "body",
        "_raw_headers",
        "_raw_body",
        "cookies",
        "auth",
        "routes",
        "hook",
        "query",
        "is_valid",
        "error",
    ]

    def __init__(self):
        #: HTTP verb to send to the server.
        self.method = None
        #: HTTP URL to send the request to.
        self.url = None
        #: dictionary of HTTP headers.
        self.headers = None
        #: HTTP path
        self.path = None
        # The cookies set used to create Cookie header
        self.cookies = None
        #: request body to send to the server.
        self.body = None
        # The raw header
        self._raw_headers = None
        #: The raw body
        self._raw_body = None
        #: Routes
        self.routes = {}
        #: Hook point for routed mapped-path
        self.hook = None
        #: Authentication tuple (username, password) if parsed
        self.auth = None
        #: Parsed query parameters
        self.query = {}
        #: Request validity flag
        self.is_valid = False
        #: Validation error description
        self.error = ""

    def extract_request_line(self, request):
        """Parse request line into method, path, and version."""
        lines = request.splitlines()
        if not lines:
            return None, None, None

        first_line = lines[0].strip()
        parts = first_line.split()
        if len(parts) != 3:
            return None, None, None

        method, path, version = parts
        return method.upper(), path, version

    def _normalize_path(self, raw_path):
        """Normalize URL path for route lookup and static resolution."""
        parsed_url = urlsplit(raw_path)
        path = parsed_url.path or "/"

        # Preserve root semantics used by this assignment skeleton.
        if path == "/":
            path = "/index.html"

        # Accept both '/path' and '/path/' for handler matching.
        if path != "/" and path.endswith("/"):
            path = path[:-1]

        query = parse_qs(parsed_url.query, keep_blank_values=True)
        query_map = {}
        for key, value in query.items():
            query_map[key] = value[0] if len(value) == 1 else value

        return path, query_map

    def prepare_headers(self, request):
        """Parse HTTP headers into a case-insensitive dictionary."""
        lines = request.split("\r\n")
        headers = CaseInsensitiveDict()
        for line in lines[1:]:
            if not line or ":" not in line:
                continue
            key, val = line.split(":", 1)
            headers[key.strip()] = val.strip()
        return headers

    def fetch_headers_body(self, request):
        """Split an HTTP message into raw headers and raw body."""
        parts = request.split("\r\n\r\n", 1)
        raw_headers = parts[0]
        raw_body = parts[1] if len(parts) > 1 else ""
        return raw_headers, raw_body

    def prepare(self, request, routes=None):
        """Prepare and validate the incoming HTTP message."""

        # Reset request state for re-use safety.
        self.method = None
        self.path = None
        self.version = None
        self.url = None
        self.headers = CaseInsensitiveDict()
        self.body = ""
        self._raw_headers = ""
        self._raw_body = ""
        self.cookies = CaseInsensitiveDict()
        self.auth = None
        self.routes = routes or {}
        self.hook = None
        self.query = {}
        self.is_valid = False
        self.error = ""

        if isinstance(request, (bytes, bytearray)):
            request = request.decode("utf-8", errors="replace")

        if not request or not str(request).strip():
            self.error = "Empty request"
            return

        self._raw_headers, self._raw_body = self.fetch_headers_body(str(request))
        method, raw_path, version = self.extract_request_line(self._raw_headers)

        if not method or not raw_path or not version:
            self.error = "Malformed request line"
            return

        normalized_path, query_map = self._normalize_path(raw_path)
        self.method = method
        self.path = normalized_path
        self.version = version
        self.url = raw_path
        self.query = query_map

        self.headers = self.prepare_headers(self._raw_headers)
        self.body = self._raw_body

        cookie_header = self.headers.get("Cookie", "")
        if cookie_header:
            self.cookies = self.parse_cookies(cookie_header)

        if self.routes:
            self.hook = self.routes.get((self.method, self.path))

        self.is_valid = True

    def prepare_body(self, data, files, json_data=None):
        """Prepare body and update content-related headers."""
        if json_data:
            self.body = json.dumps(json_data)
            self.headers["Content-Type"] = "application/json"
        elif data:
            self.body = data
            if "Content-Type" not in self.headers:
                self.headers["Content-Type"] = "text/plain"
        elif files:
            # Not implemented
            pass
        else:
            self.body = ""

        self.prepare_content_length(self.body)

    def prepare_content_length(self, body):
        """Set Content-Length from body bytes/str."""
        if body:
            length = len(body.encode("utf-8")) if isinstance(body, str) else len(body)
            self.headers["Content-Length"] = str(length)
        else:
            self.headers["Content-Length"] = "0"

    def prepare_auth(self, auth, url=""):
        """Parse Authorization header to an auth tuple when possible."""
        if not auth:
            self.auth = None
            return

        if isinstance(auth, str):
            try:
                if auth.lower().startswith("basic "):
                    encoded = auth.split(" ", 1)[1]
                    decoded = base64.b64decode(encoded).decode("utf-8")
                    self.auth = tuple(decoded.split(":", 1))
                else:
                    self.auth = auth
            except Exception:
                self.auth = None
        elif isinstance(auth, tuple) and len(auth) == 2:
            self.auth = auth
        else:
            self.auth = None

        self.url = url

    def prepare_cookies(self, cookies):
        self.headers["Cookie"] = cookies
        if "Cookie" in self.headers:
            self.cookies = self.parse_cookies(self.headers["Cookie"])

    def parse_cookies(self, cookies_header):
        """Parse Cookie header into key/value dictionary."""
        cookies = CaseInsensitiveDict()
        for cookie in cookies_header.split(";"):
            if "=" in cookie:
                key, value = cookie.strip().split("=", 1)
                cookies[key.strip()] = value.strip()
        return cookies

    def extract_credentials_from_body(self):
        """Extract username/password from JSON or form-encoded request body."""
        if not self.body:
            return None

        content_type = self.headers.get("Content-Type", "")

        if "application/json" in content_type:
            try:
                payload = json.loads(self.body)
            except (TypeError, ValueError):
                return None

            username = payload.get("username") or payload.get("user")
            password = payload.get("password") or payload.get("pass")
            if username and password:
                return str(username), str(password)
            return None

        if "application/x-www-form-urlencoded" in content_type:
            form = parse_qs(self.body, keep_blank_values=True)
            username = form.get("username", [None])[0] or form.get("user", [None])[0]
            password = form.get("password", [None])[0] or form.get("pass", [None])[0]
            if username and password:
                return str(username), str(password)

        return None
