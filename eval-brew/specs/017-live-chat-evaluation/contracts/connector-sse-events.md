# Contract: Connector SSE Events

The connector streams SSE events in response to a turn POST. The server consumes this stream and relays events to the browser.

## Wire Format

Standard SSE format (RFC):

```
event: <event-type>
data: <JSON payload>

```

A blank line terminates each event.

## Required Event Types

### `token`

An intermediate chunk of the chatbot's response. Zero or more `token` events precede the `contract` event.

```
event: token
data: {"content": "Hello, how can I"}

```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | yes | One chunk of the chatbot's response text. May be a single word, a partial word, or a sentence fragment. |

The server concatenates all `content` values in arrival order to assemble the full response.

### `contract`

The final event in the stream. Carries the complete Standard Evaluation Contract for this turn. This event signals the end of the connector stream.

```
event: contract
data: {"utterance": "...", "chatbotResponse": "...", "evaluationScores": [], ...}

```

The payload is the full Standard Evaluation Contract as defined in the existing batch-mode contract schema (Feature 006). The server validates the payload against the contract schema before invoking the evaluator.

## Stream Completion Rules

- The stream MUST end with exactly one `contract` event.
- After the `contract` event the connector MUST close the SSE connection.
- Any additional events after `contract` are ignored by the server.
- If the stream closes before a `contract` event is received, the turn fails with `error_stage = connector_stream`.
- If the `contract` event payload fails contract validation, the turn fails with `error_stage = connector_normalization` and the evaluator is NOT invoked.

## Stall Timeout

If no event is received within `ChatSession.connector_timeout_seconds` of the previous event (or the connection opening), the server treats the stream as stalled and fails the turn with `error_stage = connector_stream`.
