# Implementation Roadmap and File Placement

This document keeps all existing implementation spots, adds more assignment-required tasks, and reorganizes everything into a professional, easier-to-follow execution plan.

## 1) Scope and Priority Legend

- P0: Mandatory first (blocks core server and grading demo).
- P1: Mandatory assignment features (authentication and hybrid chat requirements).
- P2: Strongly recommended quality and reliability tasks.
- P3: Optional enhancements.

## 2) Professional Structure for Application Layer and Frontend

Use the current skeleton as runtime layout, and add clear layers for maintainability.

### 2.1 Runtime layout to keep

- daemon/: network and HTTP framework runtime.
- apps/: route handlers and business logic.
- www/: HTML pages served by server.
- static/: CSS, JS, images served by server.
- config/: proxy routing config.

### 2.2 Suggested professional structure for new implementation files

Suggested application-layer placement (inside apps/):

- apps/auth/
  - handlers.py: login/logout/auth endpoints.
  - service.py: credential validation and auth flow.
  - session_store.py: cookie/session state and expiry.
- apps/tracker/
  - handlers.py: submit-info, add-list, get-list APIs.
  - registry.py: active-peer registry and lookup.
- apps/chat/
  - handlers.py: connect-peer, broadcast-peer, send-peer APIs.
  - peer_service.py: P2P connection management.
  - channel_service.py: channel join/list/message rules.
  - protocol.py: message envelope schema and command constants.
- apps/common/
  - errors.py: shared app errors and HTTP mapping.
  - validators.py: payload validation.

Suggested frontend source placement (separate source from runtime files):

- frontend/
  - pages/
    - login.html
    - chat.html
    - form.html
  - assets/
    - css/styles.css
    - js/api.js
    - js/chat-ui.js
    - js/polling.js
  - README.md

Publish frontend source to runtime folders:

- frontend/pages -> www/
- frontend/assets/css -> static/css/
- frontend/assets/js -> static/js/
- frontend/assets/images -> static/images/

Suggested helper script location:

- scripts/sync_frontend.sh (or scripts/sync_frontend.py) to copy frontend sources into www/static before run.

## 3) Phased Implementation Checklist

## Phase P0 - Core Server Completion (Must implement first)

- [x] T01: Backend connection handling and non-blocking strategy selection
  - Target: concurrent incoming connection handling in backend daemon.
  - Spot: [daemon/backend.py](daemon/backend.py).
  - Why must: current accept loop has TODO and incomplete branch logic.
  - Done when: threading mode spawns per-client worker; callback mode dispatches correctly; coroutine mode runs with asyncio path.

- [x] T02: Proxy incoming connection concurrency
  - Target: each proxy client handled concurrently.
  - Spot: [daemon/proxy.py](daemon/proxy.py).
  - Why must: run loop has TODO after accept.
  - Done when: proxy creates worker thread per accepted client and remains responsive.

- [x] T03: Complete request parsing pipeline
  - Target: parse request line, headers, body, cookies, and route hook.
  - Spot: [daemon/request.py](daemon/request.py).
  - Why must: headers/hook/body state currently incomplete and can crash.
  - Done when: Request object consistently contains method/path/version/headers/body/cookies/hook.

- [x] T04: Execute route handlers for sync and async functions
  - Target: AsynapRous handlers are actually invoked and returned payload used.
  - Spot: [daemon/httpadapter.py](daemon/httpadapter.py), [apps/sampleapp.py](apps/sampleapp.py).
  - Why must: hooks are discovered but not executed correctly.
  - Done when: POST /login, POST /echo, PUT /hello return valid HTTP responses.

- [x] T05: Build valid HTTP response bytes
  - Target: full response = status line + headers + CRLF + body.
  - Spot: [daemon/response.py](daemon/response.py).
  - Why must: undefined symbols and incomplete header formatting block serving.
  - Done when: header builder is deterministic; Content-Length is correct; bytes sent are browser-compatible.

- [x] T06: Static object serving correctness
  - Target: serve html/css/js/images from runtime folders.
  - Spot: [daemon/response.py](daemon/response.py), [www/index.html](www/index.html), [static/css/styles.css](static/css/styles.css).
  - Why must: assignment demo needs web pages and static assets.
  - Done when: /index.html and referenced CSS/images load with proper MIME type.

- [x] T07: Proxy route policy resolution and multi-upstream behavior
  - Target: parse and apply dist_policy with multiple proxy_pass entries.
  - Spot: [start_proxy.py](start_proxy.py), [daemon/proxy.py](daemon/proxy.py), [config/proxy.conf](config/proxy.conf).
  - Why must: route resolver has undefined variable path and incomplete policy handling.
  - Done when: single-upstream and multi-upstream hosts forward predictably (round-robin baseline).

- [x] T08: Python compatibility blockers
  - Target: modern import compatibility and utility correctness.
  - Spot: [daemon/utils.py](daemon/utils.py), [daemon/dictionary.py](daemon/dictionary.py).
  - Why must: legacy imports can break execution.
  - Done when: utilities run under current Python interpreter without import errors.

## Phase P1 - Assignment-Mandatory Features

- [x] T09: HTTP authentication via headers
  - Target: RFC-inspired auth flow with WWW-Authenticate and Authorization support.
  - Spot: [daemon/request.py](daemon/request.py), [daemon/response.py](daemon/response.py), [daemon/httpadapter.py](daemon/httpadapter.py), apps/auth/handlers.py.
  - Why must: assignment section 2.2 requires authentication mechanism.
  - Done when: unauthorized request returns 401 + challenge; valid credentials allow access.

- [x] T10: Cookie-based authentication/session tracking
  - Target: Set-Cookie and Cookie parsing and access control.
  - Spot: [daemon/request.py](daemon/request.py), [daemon/response.py](daemon/response.py), apps/auth/session_store.py.
  - Why must: assignment explicitly requests cookie handling and access control.
  - Done when: login issues cookie and protected endpoints validate session cookie.

- [x] T11: Client-server initialization APIs for hybrid chat
  - Target: implement peer registration/tracker APIs.
  - Spot: apps/tracker/handlers.py, apps/tracker/registry.py, [daemon/httpadapter.py](daemon/httpadapter.py).
  - Required APIs: /submit-info, /add-list, /get-list.
  - Why must: assignment section 2.3 initialization phase.
  - Done when: peers can register, list active peers, and discover endpoints.

- [ ] T12: Peer-to-peer live messaging APIs
  - Target: direct and broadcast messaging between peers.
  - Spot: apps/chat/handlers.py, apps/chat/peer_service.py.
  - Required APIs: /connect-peer, /broadcast-peer, /send-peer.
  - Why must: assignment section 2.3 peer chatting phase.
  - Done when: peer can connect, send direct message, and broadcast to connected peers.

- [ ] T13: Channel management behaviors
  - Target: channel list, message view, submit, notifications, immutable messages.
  - Spot: apps/chat/channel_service.py, frontend/pages/chat.html, frontend/assets/js/chat-ui.js.
  - Why must: assignment section 2.3 core functional requirements.
  - Done when: user sees joined channels and incoming updates, messages cannot be edited/deleted.

- [ ] T14: Non-blocking communication among multi-daemons and peers
  - Target: apply callback/coroutine/threading strategy consistently where required.
  - Spot: [daemon/backend.py](daemon/backend.py), [daemon/proxy.py](daemon/proxy.py), apps/chat/peer_service.py.
  - Why must: assignment section 2.1 and section 2.3 task requirements.
  - Done when: concurrency model selected and documented; communication stays responsive under multiple clients.

- [ ] T15: Protocol design and message schema
  - Target: define message format, command types, and error payload structure.
  - Spot: apps/chat/protocol.py, docs/protocol.md.
  - Why must: assignment requires protocol design and processing procedure.
  - Done when: all APIs and peer messages follow one schema with versioned fields.

## Phase P2 - Reliability, Security, and Maintainability

- [ ] T16: Robust host parsing and proxy error handling
  - Target: safe handling for missing Host header or invalid route mapping.
  - Spot: [daemon/proxy.py](daemon/proxy.py).
  - Keep information: replaces dummy fallback with explicit 400/404 behavior.

- [ ] T17: Request/response defensive coding
  - Target: malformed request handling, structured error responses, timeout handling.
  - Spot: [daemon/request.py](daemon/request.py), [daemon/httpadapter.py](daemon/httpadapter.py), [daemon/response.py](daemon/response.py).

- [ ] T18: Security hardening for file serving
  - Target: prevent path traversal and unauthorized file access.
  - Spot: [daemon/response.py](daemon/response.py).

- [ ] T19: Improve startup validation and runtime diagnostics
  - Target: validate IP/port and log mode selection and route table cleanly.
  - Spot: [daemon/asynaprous.py](daemon/asynaprous.py), [start_backend.py](start_backend.py), [start_proxy.py](start_proxy.py), [start_sampleapp.py](start_sampleapp.py).

- [ ] T20: Code quality baseline
  - Target: align to PEP 8 and PEP 257 as required by assignment.
  - Spot: whole repo, starting from daemon and apps modules.

## Phase P3 - Optional Enhancements

- [ ] T21: Extended MIME type support and caching policy
  - Spot: [daemon/response.py](daemon/response.py).

- [ ] T22: Advanced proxy policies (least-conn/random/weighted)
  - Spot: [start_proxy.py](start_proxy.py), [daemon/proxy.py](daemon/proxy.py).

- [ ] T23: Asyncio-first runtime profile
  - Spot: [daemon/backend.py](daemon/backend.py), [daemon/httpadapter.py](daemon/httpadapter.py).

- [ ] T24: Better frontend packaging and sync automation
  - Spot: frontend/, scripts/sync_frontend.sh.

## 4) Quick Ownership Map (who edits what)

- Infrastructure/runtime layer: daemon/*.py.
- Application layer: apps/auth/*, apps/tracker/*, apps/chat/*.
- Frontend layer: frontend/pages/* and frontend/assets/*.
- Runtime-served artifacts: www/* and static/*.
- Process entry points: start_backend.py, start_proxy.py, start_sampleapp.py.

## 5) Suggested Implementation Order (practical)

1. Complete P0 tasks T01-T08 so server and proxy are stable.
2. Implement P1 tasks T09-T15 to satisfy assignment mandatory features.
3. Implement P2 tasks T16-T20 for robust demo and report quality.
4. Implement P3 tasks if time permits.

## 6) Deliverable Checklist Before Submission

- [ ] Proxy, backend, and webapp processes can start and communicate.
- [ ] Non-blocking mechanism is implemented and demonstrated.
- [ ] Authentication (header + cookie) works.
- [ ] Hybrid chat features (client-server + peer-to-peer) work.
- [ ] Error handling and concurrency behavior are demonstrated.
- [ ] Report includes protocol design and implementation notes.
- [ ] Source follows coding style and submission packaging rules.
