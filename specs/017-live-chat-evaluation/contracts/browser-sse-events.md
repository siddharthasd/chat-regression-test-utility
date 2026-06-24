# Contract: Browser SSE Events (Server → Browser)

The server relays connector and evaluator events to the browser via a per-turn SSE endpoint. The browser opens this endpoint after submitting a message.

## Endpoint

```
GET /chat/sessions/{session_id}/turns/{turn_id}/stream
Accept: text/event-stream
```

Authentication: same session cookie / MSAL token as all other authenticated routes.

## Behaviour on Connect

- **Turn `in_progress`**: Server replays all buffered events from the beginning of the turn (cursor = 0), then streams live events as they arrive.
- **Turn `completed` or `failed`**: Server replays all persisted events from DB and then sends a terminal event (`turn_complete` or `turn_failed`), then closes the stream.
- **Turn not found or not owned by caller**: HTTP 404 before SSE stream opens.

## Event Types

### `connector_token`

Forwarded connector `token` event. Arrives during the connector streaming phase.

```
event: connector_token
data: {"content": "Hello, how can I"}

```

| Field | Type | Description |
|-------|------|-------------|
| `content` | string | One chunk of the chatbot response text |

### `evaluating`

Signals that connector streaming has completed and evaluator invocation is starting.

```
event: evaluating
data: {}

```

### `evaluator_event`

Forwarded evaluator event. Arrives zero or more times during the evaluator streaming phase.

```
event: evaluator_event
data: {"event_type": "score_update", "payload": {"dimension": "relevance", "score": 0.82}}

```

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | The evaluator's event type (one of the five defined types, or a raw unknown string) |
| `payload` | object | The evaluator event's JSON payload verbatim |

### `turn_complete`

Signals successful completion of the full connector + evaluator pipeline.

```
event: turn_complete
data: {"turn_id": "abc123", "assembled_response": "...full assembled text..."}

```

| Field | Type | Description |
|-------|------|-------------|
| `turn_id` | string | The turn's ID |
| `assembled_response` | string | Full assembled chatbot response (concatenation of all token chunks) |

After this event the server closes the SSE stream for this turn.

### `turn_failed`

Signals a failure at any stage of the pipeline.

```
event: turn_failed
data: {"turn_id": "abc123", "error_stage": "connector_stream", "error_details": "Stall timeout exceeded"}

```

| Field | Type | Description |
|-------|------|-------------|
| `turn_id` | string | The turn's ID |
| `error_stage` | string | `connector_stream` \| `connector_normalization` \| `evaluator_stream` \| `server_restart` |
| `error_details` | string | Human-readable failure description |

After this event the server closes the SSE stream for this turn.

## Browser Reconnection

If the browser disconnects mid-turn and reconnects to the same endpoint, the server replays all buffered events from the beginning (cursor = 0). The browser must handle receiving duplicate events on reconnect by re-rendering from scratch (clearing the current pane content and replaying).

## Security

- The per-turn SSE endpoint enforces owner-only access: the requesting user's OID must match `ChatSession.owner_oid`.
- Admins may NOT subscribe to another user's turn stream.
