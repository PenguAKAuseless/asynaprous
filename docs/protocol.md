# Asynaprous Chat Protocol (v1.0)

## 1) Envelope

All peer-to-peer and channel replication messages use a common JSON envelope:

```json
{
  "version": "1.0",
  "command": "send-peer",
  "sender": "alice",
  "timestamp": 1713630000,
  "payload": {
    "message": "hello"
  }
}
```

Fields:

- `version` (string): Protocol version. Current value is `1.0`.
- `command` (string): Message command type.
- `sender` (string): Logical sender id/name.
- `timestamp` (int): Unix timestamp (seconds).
- `payload` (object): Command-specific body.

## 2) Command Types

- `connect-peer`: Peer connection metadata exchange.
- `send-peer`: Direct peer message.
- `broadcast-peer`: Broadcast to all connected peers.
- `channel-message`: Channel replication payload for `/api/receive-channel`.

## 3) Error Payload

Application errors return:

```json
{
  "status": "error",
  "error": {
    "code": "invalid-json",
    "message": "Invalid JSON"
  }
}
```

## 4) Processing Procedure

1. Parse JSON body.
2. If envelope structure is present and valid (`version`, `command`, `payload`), process by `command`.
3. If envelope is absent, fallback to legacy payload keys (`from`, `msg`, `message`, `channel`).
4. Validate required fields (`message`, target peer, endpoint fields).
5. Write immutable message to channel storage when applicable.
6. Return success/error JSON response.

## 5) Compatibility

Handlers preserve backward compatibility with earlier payloads while preferring envelope format in inter-peer forwarding.
