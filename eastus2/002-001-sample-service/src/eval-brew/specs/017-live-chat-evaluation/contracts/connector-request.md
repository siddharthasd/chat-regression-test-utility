# Contract: Connector Request (Per Turn)

The server POSTs this body to the connector's registered `endpoint_url` for each chat turn.

## Method & Headers

```
POST {connector_endpoint_url}
Content-Type: application/json
Accept: text/event-stream
```

Any additional headers defined in the connector's `auth_descriptor` (e.g. `Authorization: Bearer <token>`) are applied on top of these from the snapshotted `connector_auth_descriptor`.

## Request Body

```json
{
  "auth": {
    "test_id": "<plain-text test identifier>",
    "password": "<plain-text password>"
  },
  "message": "<tester's message text, verbatim>"
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `auth` | object | yes | Authentication block; always a top-level key |
| `auth.test_id` | string | yes | The plain-text test ID decrypted from `ChatSession.test_id_enc` |
| `auth.password` | string | yes | The plain-text password decrypted from `ChatSession.test_password_enc` |
| `message` | string | yes | The tester's input text exactly as typed (plain text) |

### Rules

- `auth` MUST be a distinct top-level object; credentials MUST NOT appear outside of `auth`.
- `message` contains only the current turn's user input — no conversation history is included in the body. The connector is responsible for maintaining session state using the `test_id` as the session key.
- The server decrypts credentials immediately before building the request and does not cache plain-text values across turns.

## Response

The connector MUST respond with `Content-Type: text/event-stream` and stream SSE events. See `connector-sse-events.md` for the required event types.
