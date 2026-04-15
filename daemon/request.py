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

This module provides a Request object to manage and persist
request settings (cookies, auth, proxies).
"""

import base64
import json
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
        "url",
        "headers",
        "body",
        "_raw_headers",
        "_raw_body",
        "reason",
        "cookies",
        "body",
        "routes",
        "hook",
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

    def extract_request_line(self, request):
        try:
            lines = request.splitlines()
            first_line = lines[0]
            method, path, version = first_line.split()

            if path == "/":
                path = "/index.html"
        except Exception:
            return None, None, None

        return method, path, version

    def prepare_headers(self, request):
        """Prepares the given HTTP headers."""
        lines = request.split("\r\n")
        headers = CaseInsensitiveDict()
        for line in lines[1:]:
            if ": " in line:
                key, val = line.split(": ", 1)
                headers[key] = val
        return headers

    def fetch_headers_body(self, request):
        """Prepares the given HTTP headers."""
        # Split request into header section and body section
        parts = request.split("\r\n\r\n", 1)  # split once at blank line

        _headers = parts[0]
        _body = parts[1] if len(parts) > 1 else ""
        return _headers, _body

    def prepare(self, request, routes=None):
        """Prepares the entire request with the given parameters."""

        # Prepare the request line from the request header
        print("[Request] prepare request missg {}".format(request))
        self.method, self.path, self.version = self.extract_request_line(request)
        print(
            "[Request] {} path {} version {}".format(
                self.method, self.path, self.version
            )
        )

        # @bksysnet Preapring the webapp hook with AsynapRous instance
        # The default behaviour with HTTP server is empty routed
        #
        # TODO manage the webapp hook in this mounting point
        
        if not request:
            return
        
        # Extract raw headers and body from the request
        self._raw_headers, self._raw_body = self.fetch_headers_body(request)
        # Extract first line
        self.method, self.path, self.version = self.extract_request_line(self._raw_headers)
        # Extract headers
        self.headers = self.prepare_headers(self._raw_headers)
        self.body = self._raw_body

        if routes:
            self.routes = routes
            print("[Request] Routing METHOD {} path {}".format(self.method, self.path))
            # Find handler hook for the request method and path
            self.hook = routes.get((self.method, self.path))

            # TODO manage the webapp hook in this mounting point

            if self.hook:
                print("[Request] Hook has request {}".format(request))
                self.prepare_body(data=self._raw_body, files=None, json=None)
            else:
                print("[Request] No hook for request {}".format(request))
        
        cookies_header = self.headers.get("cookie", "")
        
        #  TODO: implement the cookie function here
        #        by parsing the header            

        if cookies_header:
            self.cookies = self.parse_cookies(cookies_header)

    def prepare_body(self, data, files, json_data=None):
        
        # TODO prepare the body
        
        if json_data:
            self.body = json.dumps(json_data)
            self.headers['Content-Type'] = 'application/json'
        elif data:
            self.body = data
            if 'content-type' not in self.headers:
                self.headers['Content-Type'] = 'text/plain'
        elif files:
            # Not implemented
            pass
        else:
            self.body = ""
        
        self.prepare_content_length(self.body)

    def prepare_content_length(self, body):

        # TODO prepare the content length
        
        if body:
            # Handle multiple types of body content
            length = len(body.encode('utf-8')) if isinstance(body, str) else len(body)
            self.headers["Content-Length"] = str(length)
        else:
            self.headers["Content-Length"] = "0"

    def prepare_auth(self, auth, url=""):

        # TODO prepare the request authentication
        
        if not auth:
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

    # Helper function
    def parse_cookies(self, cookies_header):
        cookies = CaseInsensitiveDict()
        for cookie in cookies_header.split("; "):
            if "=" in cookie:
                key, value = cookie.strip().split("=", 1)
                cookies[key] = value
        return cookies
