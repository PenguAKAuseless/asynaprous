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

- [x] T12: Peer-to-peer live messaging APIs
  - Target: direct and broadcast messaging between peers.
  - Spot: apps/chat/handlers.py, apps/chat/peer_service.py.
  - Required APIs: /connect-peer, /broadcast-peer, /send-peer.
  - Why must: assignment section 2.3 peer chatting phase.
  - Done when: peer can connect, send direct message, and broadcast to connected peers.

- [x] T13: Channel management behaviors
  - Target: channel list, message view, submit, notifications, immutable messages.
  - Spot: apps/chat/channel_service.py, frontend/pages/chat.html, frontend/assets/js/chat-ui.js.
  - Why must: assignment section 2.3 core functional requirements.
  - Done when: user sees joined channels and incoming updates, messages cannot be edited/deleted.

- [x] T14: Non-blocking communication among multi-daemons and peers
  - Target: apply callback/coroutine/threading strategy consistently where required.
  - Spot: [daemon/backend.py](daemon/backend.py), [daemon/proxy.py](daemon/proxy.py), apps/chat/peer_service.py.
  - Why must: assignment section 2.1 and section 2.3 task requirements.
  - Done when: concurrency model selected and documented; communication stays responsive under multiple clients.
  - Implemented decision: threading-first runtime used as stable default for backend/proxy/peer fan-out.

- [x] T15: Protocol design and message schema
  - Target: define message format, command types, and error payload structure.
  - Spot: apps/chat/protocol.py, docs/protocol.md.
  - Why must: assignment requires protocol design and processing procedure.
  - Done when: all APIs and peer messages follow one schema with versioned fields.

## Phase P2 - Reliability, Security, and Maintainability

- [x] T16: Robust host parsing and proxy error handling
  - Target: safe handling for missing Host header or invalid route mapping.
  - Spot: [daemon/proxy.py](daemon/proxy.py).
  - Keep information: replaces dummy fallback with explicit 400/404 behavior.

- [x] T17: Request/response defensive coding
  - Target: malformed request handling, structured error responses, timeout handling.
  - Spot: [daemon/request.py](daemon/request.py), [daemon/httpadapter.py](daemon/httpadapter.py), [daemon/response.py](daemon/response.py).

- [x] T18: Security hardening for file serving
  - Target: prevent path traversal and unauthorized file access.
  - Spot: [daemon/response.py](daemon/response.py).

- [x] T19: Improve startup validation and runtime diagnostics
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

- [x] Proxy, backend, and webapp processes can start and communicate.
- [x] Non-blocking mechanism is implemented and demonstrated.
- [x] Authentication (header + cookie) works.
- [x] Hybrid chat features (client-server + peer-to-peer) work.
- [x] Error handling and concurrency behavior are demonstrated.
- [x] Report includes protocol design and implementation notes.
- [ ] Source follows coding style and submission packaging rules.

## 7) Implementation Progress (2026-04-20)

### 7.1 What was implemented

- Core HTTP request lifecycle hardening:
  - Robust request-line parsing, header/body split, Content-Length-aware reading, cookie/auth extraction.
  - Files: [daemon/request.py](daemon/request.py), [daemon/httpadapter.py](daemon/httpadapter.py).
- Response and static serving hardening:
  - Deterministic status/header builder, correct Content-Length, Set-Cookie support, 400/401/404 handling.
  - Safe static path resolution with traversal blocking.
  - Files: [daemon/response.py](daemon/response.py).
- Authentication and session control:
  - HTTP Basic challenge (`WWW-Authenticate`) for protected routes.
  - Session cookie issuance on successful login and session expiry via TTL.
  - Credentials moved to SQLite `accounts` table with salted password hash storage.
  - Hashing uses strongest available runtime option: `scrypt` (preferred) or `pbkdf2_sha512` fallback.
  - Files: [daemon/httpadapter.py](daemon/httpadapter.py), [apps/auth/handlers.py](apps/auth/handlers.py), [apps/auth/account_store.py](apps/auth/account_store.py), [apps/auth/session_store.py](apps/auth/session_store.py), [www/login.html](www/login.html).
- Hybrid chat wiring and fixes:
  - Added protocol envelope support and error schema.
  - Fixed peer/channel forwarding logic and the previous channel broadcast argument mismatch.
  - Added `/add-list` endpoint and standardized tracker/list behavior.
  - Tracker/peer remain thread-safe in-memory; channels/messages now persist in SQLite (`channels`, `channel_members`, `messages`).
  - Files: [apps/chat/protocol.py](apps/chat/protocol.py), [apps/chat/handlers.py](apps/chat/handlers.py), [apps/chat/peer_service.py](apps/chat/peer_service.py), [apps/chat/channel_service.py](apps/chat/channel_service.py), [apps/chat/message_store.py](apps/chat/message_store.py), [apps/tracker/handlers.py](apps/tracker/handlers.py), [apps/tracker/registry.py](apps/tracker/registry.py), [apps/sampleapp.py](apps/sampleapp.py).
- Proxy hardening:
  - Missing Host handling (400), unmapped host handling (404), backend failure handling (502), timeout-based forwarding.
  - Round-robin policy resolution for multiple upstreams.
  - Files: [daemon/proxy.py](daemon/proxy.py), [start_proxy.py](start_proxy.py), [config/proxy.conf](config/proxy.conf).
- Frontend behavior updates:
  - Login form fetch-based auth flow with redirect to chat.
  - Chat UI unauthorized redirect and fetch error handling.
  - Files: [www/login.html](www/login.html), [static/js/chat-ui.js](static/js/chat-ui.js).
- Circular import fix for runtime boot order:
  - Lazy loading of sampleapp in package init.
  - File: [apps/__init__.py](apps/__init__.py).

### 7.2 How it works (secure/workable path)

1. Client logs in using `POST /login`.
2. Adapter validates credentials (JSON/form body or Authorization header) against SQLite account records.
3. On success, server issues `Set-Cookie: session_id=...`.
4. Protected routes (`/api/*`, tracker and peer control APIs, `/hello`, `/logout`) require valid session or valid Basic auth.
5. Chat send flow writes immutable message objects to SQLite channel storage, then replicates to connected peers via protocol envelopes.
6. Proxy routes requests by Host header and returns explicit status codes for bad/missing routing conditions.

### 7.3 Verification evidence (executed)

Executed with running processes:

- sampleapp A: `127.0.0.1:2026`
- sampleapp B: `127.0.0.1:2027`
- backend: `127.0.0.1:9000`
- proxy: `127.0.0.1:8080`

Observed outputs:

- `GET /chat.html` on sampleapp: `status=200`
- `GET /api/channels` without auth: `status=401`
- login with valid credentials: success JSON and cookie persisted
- `GET /api/channels` with cookie: `[
  "general", "networking", "random"
]`
- channel send/get messages: returned stored immutable message object with timestamp
- peer connect and direct send (`/connect-peer`, `/send-peer`): returned `{"status": "sent"}`
- proxy default host static (`Host: 127.0.0.1:8080`, `/index.html`): `status=200`
- proxy app host login+channels (`Host: app1.local`): login success and channels returned

Database verification snapshot (executed):

- tables present in `db/asynaprous.sqlite3`: `accounts`, `channels`, `channel_members`, `messages`
- account rows present: `admin`, `user1`, `user2`, `user3`, `user4`, `user5`
- password storage check: `password_hash` and `salt` stored as hex (no plaintext password columns)
- chat persistence check: inserted message in `project-x` and retrieved same row from `messages` table

### 7.4 Demo Account Table (database-seeded)

Database file: `db/asynaprous.sqlite3`

| Username | Role | Password source (set before start) | Stored secret format | Hash algorithm column |
| --- | --- | --- | --- | --- |
| admin | administrator | `ASYNAPROUS_DEMO_PASSWORD_ADMIN` | salted hash (`accounts.password_hash`) + salt (`accounts.salt`) | `accounts.hash_algorithm` |
| user1 | member | `ASYNAPROUS_DEMO_PASSWORD_USER1` | salted hash (`accounts.password_hash`) + salt (`accounts.salt`) | `accounts.hash_algorithm` |
| user2 | member | `ASYNAPROUS_DEMO_PASSWORD_USER2` | salted hash (`accounts.password_hash`) + salt (`accounts.salt`) | `accounts.hash_algorithm` |
| user3 | member | `ASYNAPROUS_DEMO_PASSWORD_USER3` | salted hash (`accounts.password_hash`) + salt (`accounts.salt`) | `accounts.hash_algorithm` |
| user4 | member | `ASYNAPROUS_DEMO_PASSWORD_USER4` | salted hash (`accounts.password_hash`) + salt (`accounts.salt`) | `accounts.hash_algorithm` |
| user5 | member | `ASYNAPROUS_DEMO_PASSWORD_USER5` | salted hash (`accounts.password_hash`) + salt (`accounts.salt`) | `accounts.hash_algorithm` |

Recommended setup before launching processes:

```bash
export ASYNAPROUS_DEMO_PASSWORD_ADMIN='<strong-password-admin>'
export ASYNAPROUS_DEMO_PASSWORD_USER1='<strong-password-user1>'
export ASYNAPROUS_DEMO_PASSWORD_USER2='<strong-password-user2>'
export ASYNAPROUS_DEMO_PASSWORD_USER3='<strong-password-user3>'
export ASYNAPROUS_DEMO_PASSWORD_USER4='<strong-password-user4>'
export ASYNAPROUS_DEMO_PASSWORD_USER5='<strong-password-user5>'
```

Note:

- Missing password env vars fail seeding for non-existing demo users so credentials are never silently hardcoded.
- Seeding is non-destructive: existing account rows are kept and chat messages are not reset.

Backend admin command to purge database and reseed demo baseline:

```bash
python start_backend.py --purge-db-demo --yes
```

Additional executed validation:

- 2-process demo (ports 2101 and 2102):
  - create channel on peer A: `{"status": "created", "channel": "project-x", "user": "alice"}`
  - join channel on peer B: `{"status": "joined", "channel": "project-x", "user": "bob"}`
  - list joined channels for bob: `{"status": "ok", "channels": ["project-x"]}`
  - send channel message from A: `delivered: 1`
  - verify B received: `[{"sender":"alice","message":"hello-from-alice", ...}]`

- 5-process demo (backend+proxy+3 sampleapp peers):
  - tracker submit-info/add-list/get-list works with active peer list output
  - create/join channel across peers works for `project-5`
  - fanout channel message from peer 2026 delivered to peers 2027 and 2028 (`delivered: 2`)
  - broadcast-peer from 2026 delivered to both peers (`broadcast_done`, `delivered: 2`)
  - proxy web path works on launched proxy port (`default-host-status=200`)

### 7.5 Protocol design notes

- Documented in [docs/protocol.md](docs/protocol.md).
- Runtime constants and validation in [apps/chat/protocol.py](apps/chat/protocol.py).

## 8) Demo Playbook

### 8.1 Case A: One Device (single process)

Goal: validate local webapp login, channel creation, and channel messaging on one node.

Start one process:

- `python start_sampleapp.py --server-ip 127.0.0.1 --server-port 2026`

Minimal checks:

1. Open `http://127.0.0.1:2026/login.html`
2. Login with `admin` and the password configured in `ASYNAPROUS_DEMO_PASSWORD_ADMIN`
3. Create a channel from chat UI (Create button)
4. Send a message and verify it appears in the message list

Expected:

- Login returns session cookie and redirects to chat page
- Channel appears in channel list
- Message appears with timestamp and sender

### 8.2 Case B: Two Devices (2 processes)

Goal: validate peer-to-peer receive and channel registration between two peers.

Start 2 processes:

- `python start_sampleapp.py --server-ip 127.0.0.1 --server-port 2101`
- `python start_sampleapp.py --server-ip 127.0.0.1 --server-port 2102`

Terminal demo checks executed:

1. Login on both peers (store cookies)
2. Create channel `project-x` on peer 2101
3. Join channel `project-x` on peer 2102
4. Connect peers using `/connect-peer`
5. Send `/api/send-channel` on 2101 and verify `/api/get-messages` on 2102
6. Send `/send-peer` direct message and verify it appears on receiver

Observed:

- Channel create: success (`status: created`)
- Channel join: success (`status: joined`)
- Channel replication delivery: `delivered: 1`
- Receiver contained sent message payload

### 8.3 Case C: Multiple Devices (5 processes)

Goal: validate full topology and multi-peer delivery.

Start 5 processes:

1. Backend: `python start_backend.py --server-ip 127.0.0.1 --server-port 9000`
2. Sampleapp A: `python start_sampleapp.py --server-ip 127.0.0.1 --server-port 2026`
3. Sampleapp B: `python start_sampleapp.py --server-ip 127.0.0.1 --server-port 2027`
4. Sampleapp C: `python start_sampleapp.py --server-ip 127.0.0.1 --server-port 2028`
5. Proxy: `python start_proxy.py --server-ip 127.0.0.1 --server-port 18080`

Terminal demo checks executed:

1. Tracker register/list via `/submit-info`, `/add-list`, `/get-list`
2. Create/join channel `project-5` across peers
3. Connect 2026 -> 2027 and 2026 -> 2028
4. Send `/api/send-channel` from 2026
5. Verify messages received on both 2027 and 2028
6. Send `/broadcast-peer` from 2026 and verify both peers receive in `general`
7. Verify proxy web access and proxied app login/channels

Observed:

- Tracker list returned registered peer records
- Channel fanout delivery from 2026: `delivered: 2`
- Both peers received `hello-team`
- Proxy default host static status: `200`
- Proxied app login and channel list returned successfully

### 8.4 Browser Web Demo (executed)

Executed on `http://127.0.0.1:2026/login.html` then redirected to chat.

Verified UI elements and behavior:

- Login form with username/password works
- Chat page loads channel controls (Create, Join)
- Creating channel `ui-room` updates channel list
- Sending message `frontend-message` renders in chat history

### 8.5 Terminal Demo (executed)

All major APIs were verified with curl in terminal:

- Auth/session: `/login`, protected `/api/channels`
- Tracker: `/submit-info`, `/add-list`, `/get-list`
- Peer: `/connect-peer`, `/send-peer`, `/broadcast-peer`
- Channels: `/api/create-channel`, `/api/join-channel`, `/api/my-channels`, `/api/send-channel`, `/api/get-messages`
- Proxy: host-routed `/index.html`, `/login`, `/api/channels`
