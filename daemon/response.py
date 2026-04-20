#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynApRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#

"""
daemon.response
~~~~~~~~~~~~~~~~~

This module provides a Response object for building HTTP responses, serving
static content, and managing headers/cookies in a predictable way.
"""

import datetime
import json
import mimetypes
import os

from .dictionary import CaseInsensitiveDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WWW_DIR = os.path.join(BASE_DIR, "www")
STATIC_DIR = os.path.join(BASE_DIR, "static")


class Response:
    """The :class:`Response <Response>` object, which contains a
    server's response to an HTTP request.

    Instances are generated from a :class:`Request <Request>` object, and
    should not be instantiated manually; doing so may produce undesirable
    effects.

    :class:`Response <Response>` object encapsulates headers, content,
    status code, cookies, and metadata related to the request-response cycle.
    It is used to construct and serve HTTP responses in a custom web server.

    :attrs status_code (int): HTTP status code (e.g., 200, 404).
    :attrs headers (dict): dictionary of response headers.
    :attrs url (str): url of the response.
    :attrsencoding (str): encoding used for decoding response content.
    :attrs history (list): list of previous Response objects (for redirects).
    :attrs reason (str): textual reason for the status code (e.g., "OK", "Not Found").
    :attrs cookies (CaseInsensitiveDict): response cookies.
    :attrs elapsed (datetime.timedelta): time taken to complete the request.
    :attrs request (PreparedRequest): the original request object.

    Usage::

      >>> import Response
      >>> resp = Response()
      >>> resp.build_response(req)
      >>> resp
      <Response>
    """

    __attrs__ = [
        "_content",
        "_header",
        "status_code",
        "method",
        "headers",
        "url",
        "history",
        "encoding",
        "reason",
        "cookies",
        "elapsed",
        "request",
        "body",
        "_set_cookies",
    ]

    def __init__(self, request=None):
        """
        Initializes a new :class:`Response <Response>` object.

        : params request : The originating request object.
        """

        self._content = b""
        self._content_consumed = False
        self._next = None

        #: Integer Code of responded HTTP Status, e.g. 404 or 200.
        self.status_code = None

        #: Case-insensitive Dictionary of Response Headers.
        #: For example, ``headers['content-type']`` will return the
        #: value of a ``'Content-Type'`` response header.
        self.headers = CaseInsensitiveDict()

        #: URL location of Response.
        self.url = None

        #: Encoding to decode with when accessing response text.
        self.encoding = None

        #: A list of :class:`Response <Response>` objects from
        #: the history of the Request.
        self.history = []

        #: Textual reason of responded HTTP Status, e.g. "Not Found" or "OK".
        self.reason = None

        #: A of Cookies the response headers.
        self.cookies = CaseInsensitiveDict()

        #: The amount of time elapsed between sending the request
        self.elapsed = datetime.timedelta(0)

        #: The :class:`PreparedRequest <PreparedRequest>` object to which this
        #: is a response.
        self.request = None
        self._set_cookies = []

    def get_mime_type(self, path):
        """Determine MIME type from path."""
        path_lower = path.lower()
        if path_lower.endswith(".html"):
            return "text/html"
        if path_lower.endswith(".css"):
            return "text/css"
        if path_lower.endswith(".js"):
            return "application/javascript"
        
        mime_type, _ = mimetypes.guess_type(path)
        return mime_type or "application/octet-stream"

    def _resolve_base_dir(self, path, mime_type):
        """Resolve which runtime directory should serve the request path."""
        if path.startswith("/css/") or path.startswith("/js/") or path.startswith("/images/"):
            return STATIC_DIR

        if path.endswith(".html"):
            return WWW_DIR

        if mime_type.startswith("image/"):
            return STATIC_DIR

        if mime_type in ("text/css", "application/javascript", "text/javascript"):
            return STATIC_DIR

        return None

    def _safe_resolve_path(self, base_dir, path):
        """Resolve path safely and block traversal outside base_dir."""
        normalized = path.lstrip("/")
        requested = os.path.abspath(os.path.join(base_dir, normalized))
        base_abs = os.path.abspath(base_dir)

        if requested == base_abs:
            return requested

        if not requested.startswith(base_abs + os.sep):
            return None

        return requested

    def build_content(self, path, base_dir):
        """Load static file content from a safe resolved location."""
        filepath = self._safe_resolve_path(base_dir, path)
        if not filepath:
            return -1, b""

        if not os.path.isfile(filepath):
            return -1, b""

        try:
            with open(filepath, "rb") as f:
                content = f.read()
        except OSError:
            return -1, b""

        return len(content), content

    def _status_reason(self, status_code):
        status_map = {
            200: "OK",
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            500: "Internal Server Error",
            502: "Bad Gateway",
        }
        return status_map.get(status_code, "OK")

    def build_response_header(self, request):
        """Build status line and response headers as bytes."""
        status_code = self.status_code or 200
        reason = self.reason or self._status_reason(status_code)
        state_line = "HTTP/1.1 {} {}\r\n".format(status_code, reason)

        if "Content-Type" not in self.headers:
            self.headers["Content-Type"] = "application/octet-stream"
        self.headers["Content-Length"] = str(len(self._content))
        self.headers["Date"] = datetime.datetime.utcnow().strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )
        if "Connection" not in self.headers:
            self.headers["Connection"] = "close"
        if "Server" not in self.headers:
            self.headers["Server"] = "AsynapRous"

        fmt_header = state_line
        for key, value in self.headers.items():
            if isinstance(value, list):
                for item in value:
                    fmt_header += "{}: {}\r\n".format(key, item)
            else:
                fmt_header += "{}: {}\r\n".format(key, value)

        for cookie_header in self._set_cookies:
            fmt_header += "Set-Cookie: {}\r\n".format(cookie_header)

        fmt_header += "\r\n"
        return fmt_header.encode("utf-8")

    def build_notfound(self):
        """Build a standard 404 response."""
        self.status_code = 404
        self.reason = self._status_reason(404)
        self.headers["Content-Type"] = "text/plain; charset=utf-8"
        self._content = b"404 Not Found"
        return self.build_response_header(None) + self._content

    def build_bad_request(self, message="400 Bad Request"):
        """Build a standard 400 response."""
        self.status_code = 400
        self.reason = self._status_reason(400)
        self.headers["Content-Type"] = "text/plain; charset=utf-8"
        self._content = message.encode("utf-8")
        return self.build_response_header(None) + self._content

    def build_response(self, request, envelop_content=None):
        """Build a complete HTTP response from dynamic payload or static file."""
        path = request.path if request else "/index.html"
        if path in ("", "/"):
            path = "/index.html"

        self.status_code = self.status_code or 200
        self.reason = self.reason or self._status_reason(self.status_code)

        if envelop_content is not None:
            if isinstance(envelop_content, (dict, list)):
                self._content = json.dumps(envelop_content).encode("utf-8")
            elif isinstance(envelop_content, str):
                self._content = envelop_content.encode("utf-8")
            else:
                self._content = envelop_content

            if "Content-Type" not in self.headers:
                self.headers["Content-Type"] = "application/json; charset=utf-8"
        else:
            mime_type = self.get_mime_type(path)
            base_dir = self._resolve_base_dir(path, mime_type)
            if not base_dir:
                return self.build_notfound()

            length, content = self.build_content(path, base_dir)
            if length < 0:
                return self.build_notfound()

            self._content = content
            self.headers["Content-Type"] = mime_type

        self._header = self.build_response_header(request)
        return self._header + self._content

    def build_unauthorized(self, realm="AsynapRous", include_challenge=True):
        """Build a 401 response with optional HTTP auth challenge header."""
        self.status_code = 401
        self.reason = self._status_reason(401)
        self.headers.pop("WWW-Authenticate", None)
        if include_challenge:
            self.headers["WWW-Authenticate"] = 'Basic realm="{}"'.format(realm)
        self.headers["Content-Type"] = "text/html; charset=utf-8"
        self._content = b"<h1>401 Unauthorized</h1>"
        return self.build_response_header(None) + self._content

    def set_cookie(
        self,
        key,
        value,
        max_age=3600,
        path="/",
        http_only=True,
        same_site="Lax",
        secure=False,
    ):
        """Append Set-Cookie header entries for the response."""
        cookie_parts = [
            "{}={}".format(key, value),
            "Max-Age={}".format(int(max_age)),
            "Path={}".format(path),
        ]
        if http_only:
            cookie_parts.append("HttpOnly")
        if same_site:
            cookie_parts.append("SameSite={}".format(same_site))
        if secure:
            cookie_parts.append("Secure")

        self._set_cookies.append("; ".join(cookie_parts))