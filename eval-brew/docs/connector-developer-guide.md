# Building a Connector — Developer Guide

This guide is for developers building a **connector**: an HTTP service that sits
between the regression harness and your chatbot. You deploy the connector in your own
environment, then register it in the harness by entering its metadata (URL, auth,
timeout). This document covers the request/response contract, the validation the
harness applies, the error categories you'll be graded against, and the registration
steps.

---

## 1. What a connector is

For each test row, the harness makes **one HTTP `POST`** to your connector with the
utterance to test. Your connector calls your chatbot however it needs to, then returns
a **Standard Evaluation Contract** — a normalized JSON envelope describing the chatbot's
response. The harness validates that envelope and hands it to the evaluation agent.

```
harness ──POST {testId, utteranceText, password?}──▶ YOUR CONNECTOR ──▶ your chatbot
harness ◀──── Standard Evaluation Contract (JSON) ───┘
```

Your connector is the only part you write. It must:

1. Accept the harness's `POST` request.
2. Call your chatbot.
3. Return a contract-conformant JSON body with HTTP `200`.

Connectors are **stateless** from the harness's point of view: every row is an
independent request. There is no session, no `connect`/`disconnect`.

---

## 2. The request the harness sends you

| Aspect | Value |
|---|---|
| Method | `POST` |
| URL | Your registered `endpointUrl` (called verbatim for every row) |
| `Content-Type` | `application/json` |
| Auth header | Added by the harness per your registered auth mode (see §6) |
| Timeout | The harness aborts the call after your registered `timeoutSeconds`; it does **not** retry |

**Body:**

```json
{
  "testId": "hours-001",
  "utteranceText": "What are your opening hours?",
  "password": "hunter2"
}
```

- `testId` *(string)* — the test-case id from the CSV row. Echo it back in your response.
- `utteranceText` *(string)* — the message to send to the chatbot. Echo it back.
- `password` *(string, optional)* — present **only if** your registration has
  *expects-per-row-password* enabled (see §7). Use it to authenticate to your chatbot;
  do **not** echo it back anywhere in your response.

Your endpoint should ignore unknown fields (the harness may add fields additively in
future versions).

---

## 3. The response you must return — Standard Evaluation Contract

Return HTTP **`200`** with a JSON body matching the contract below. The schema is
JSON Schema draft 2020-12; **additional properties are allowed at every level**, so you
may include extra fields, but the required ones must be present and well-typed.

### Top-level fields

Required unless noted.

| Field | Type | Notes |
|---|---|---|
| `contractVersion` | string | Integer-as-string. **Use `"1"`.** Compared numerically; a value *ahead* of the harness's bundled version is rejected. |
| `utteranceId` | string | A globally-unique id you generate per response (UUID v4 recommended). Used to correlate this row through to the evaluator, which must echo it back. |
| `utteranceText` | string | Echo the request's `utteranceText`. |
| `testId` | string | Echo the request's `testId`. |
| `conversationContext` | object \| null | **Must be `null` in v1** (reserved for future multi-turn). |
| `connectorId` | string | A stable identifier for your connector service (any non-empty string). |
| `timestamp` | string | RFC 3339 / ISO-8601 datetime, e.g. `2026-06-05T14:32:00Z`. |
| `chatbotResponse` | object | The chatbot's answer; see below. |
| `tokenUsage` | object \| omitted | **Optional.** LLM token counts for this chatbot call; see below. Omit entirely for non-LLM connectors. |

### `chatbotResponse` object (all four sub-fields required)

| Field | Type | Notes |
|---|---|---|
| `rawPayload` | any | The raw chatbot response exactly as you received it. Shape is unconstrained (object, array, string, …). Preserved for diagnosis. |
| `normalizedText` | string | Your best plain-text rendering of what the chatbot said. **Empty string is allowed** (e.g. if the bot returned only structured data). |
| `agentChain` | array of strings | Ordered agent identifiers invoked, if your bot is agentic. **`[]` is valid** for non-agentic bots. |
| `metadata` | object | Free-form connector-specific metadata (latency, model name, …). No keys are standardized. **`{}` is valid.** For LLM token counts, use the top-level `tokenUsage` field instead. |

### `tokenUsage` object (optional)

Report LLM token consumption for the chatbot call. Omit the key entirely for non-LLM
connectors — `null` and an empty object are treated the same as omission. All three
sub-fields are themselves optional; include whichever your LLM SDK exposes.

| Field | Type | Notes |
|---|---|---|
| `promptTokens` | integer ≥ 0 | Tokens consumed by the prompt / input. |
| `completionTokens` | integer ≥ 0 | Tokens consumed by the completion / output. |
| `totalTokens` | integer ≥ 0 | Total tokens consumed. **The harness uses this value for per-row and job-level token aggregation.** |

The harness adds `totalTokens` from the connector and evaluator responses to produce a
**row total**, then sums row totals to produce a **job-level token count** included in
every export.

> **Do not put the per-row `password` anywhere in the response** — not in `rawPayload`,
> `metadata`, or any other field. The harness asserts connectors don't echo credentials.

### Complete example response

```json
{
  "contractVersion": "1",
  "utteranceId": "a3f1c2de-9b44-4e7a-8c11-2b6f0d9e1234",
  "utteranceText": "What are your opening hours?",
  "testId": "hours-001",
  "conversationContext": null,
  "connectorId": "acme-support-bot",
  "timestamp": "2026-06-05T14:32:00Z",
  "chatbotResponse": {
    "rawPayload": { "answer": "We're open 9–5, Mon–Fri.", "intent": "store_hours", "confidence": 0.97 },
    "normalizedText": "We're open 9 to 5, Monday through Friday.",
    "agentChain": ["intent-classifier", "kb-retriever"],
    "metadata": { "latencyMs": 412, "model": "acme-llm-v3" }
  },
  "tokenUsage": { "promptTokens": 412, "completionTokens": 78, "totalTokens": 490 }
}
```

### Versioning rule

The contract is **additive-only**: new optional fields may be added over time without
bumping `contractVersion`. Always send `contractVersion: "1"`. A higher value is treated
as "from a newer harness than this one" and the row is failed at validation. Because
additional properties are allowed, you can include forward-looking fields safely.

---

## 4. Reference implementation (Python/Flask sketch)

Any HTTP server in any language works. A minimal connector:

```python
import uuid
from datetime import datetime, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.post("/connect")
def connect():
    body = request.get_json(force=True)
    test_id = body["testId"]
    utterance = body["utteranceText"]
    password = body.get("password")  # present only if the harness forwards it

    raw = call_my_chatbot(utterance, password)   # <- your integration

    return jsonify({
        "contractVersion": "1",
        "utteranceId": str(uuid.uuid4()),
        "utteranceText": utterance,
        "testId": test_id,
        "conversationContext": None,
        "connectorId": "acme-support-bot",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "chatbotResponse": {
            "rawPayload": raw,
            "normalizedText": extract_text(raw),
            "agentChain": [],
            "metadata": {},
        },
    }), 200
```

The harness ships a **bundled mock connector** you can read and run as a worked
reference — see §8.

---

## 5. How the harness grades your response — error categories

The harness records one of these per-row outcomes. The four `connector_*` stages are
the ones your service influences; understanding them tells you exactly what to avoid.

| Stage | When it happens | How to avoid it |
|---|---|---|
| *(success)* | You returned `200` with a schema-valid contract | — |
| `connector_transport` | The harness couldn't reach you, the connection failed (DNS/refused/TLS), or your response took longer than `timeoutSeconds` | Be reachable; respond within the configured timeout; the harness will **not** retry |
| `connector_response` | You returned a **non-2xx** HTTP status. The harness records your response body (truncated) as the error detail | Return `200`; put diagnostic info in the body if you must fail |
| `connector_normalization` | You returned `2xx` but the body **isn't valid JSON**, or it **fails contract validation** (missing/mis-typed required field, `contractVersion` too high). The detail lists the field violations | Match the schema in §3 exactly; send `contractVersion: "1"`; ensure `conversationContext` is `null` and `chatbotResponse` has all four sub-fields |
| `connector_auth` | The harness couldn't obtain the service credential — either it couldn't **decrypt the stored credential** (machine key missing/rotated) or, for `client-credentials`, the **token request failed** (token URL unreachable, non-2xx, or no `access_token`) | Decrypt failures are a harness-side config issue (re-register the credential); token failures mean checking the token URL / client id / client secret / scope you registered |

Per-row failures are **isolated**: a failing row is recorded with its stage + detail and
the run continues. One bad row never aborts the job.

---

## 6. Authentication

Your endpoint can require auth. The harness attaches the header based on the **auth mode**
chosen at registration; you implement the matching check on your side.

| Auth mode | Header the harness sends | You implement |
|---|---|---|
| `none` | *(none)* | Open endpoint (use network controls instead) |
| `bearer` | `Authorization: Bearer <token>` | Validate the bearer token |
| `api-key-header` | `<your-header-name>: <value>` | Validate a custom header (e.g. `X-API-Key`) |
| `basic` | `Authorization: Basic base64(user:pass)` | Validate HTTP Basic credentials |
| `client-credentials` | `Authorization: Bearer <fetched-token>` | Validate the bearer token your gateway/IdP issued |

The credential is entered once at registration and **encrypted at rest** by the harness;
it is decrypted only in memory when building each request and never logged, exported, or
shown in the UI. This auth is **service-level** (how the harness authenticates to your
connector) and is distinct from the optional **per-row `password`** (§7), which is a
credential for your *chatbot*.

For `client-credentials`, the harness performs the OAuth2 **client-credentials grant** itself:
before calling your endpoint it `POST`s `grant_type=client_credentials` (plus your client id,
client secret, and optional scope/audience) as a form-encoded body to your registered **token
URL**, reads the `access_token` from the JSON response, and attaches it as
`Authorization: Bearer <token>`. Tokens are cached in memory and reused until shortly before
their `expires_in`, then re-fetched — so your endpoint just validates a normal bearer token.
If the token request fails (unreachable token URL, non-2xx, or no `access_token`), the row is
recorded under the `connector_auth` stage and your endpoint is never called.

> **This token is service-level — one token, the same for every row.** The harness's
> client-credentials grant carries only your registered client id/secret/scope/audience; it has
> **no per-row parameter**, and the token is cached and reused across all rows of a job. If your
> backend needs a **per-employee / per-end-user** token, do *not* try to drive it from this
> credential. Instead, key it off the per-row **`testId`** that every connector request already
> carries in its body (§2), and mint the per-user token **inside your connector**. In other
> words: the harness uses one service token to *reach* you; your connector uses `testId` to
> obtain whatever per-user token it needs to call the chatbot. (If the per-user secret is a
> password rather than a derived identity, use the per-row `password` in §7 instead.)

---

## 7. Per-row password (optional)

If your chatbot needs a **different credential per test row** (e.g. impersonating
different end-user accounts), enable *expects-per-row-password* on the registration.
Then:

- The CSV uploaded for the job **must** include a `password` column with a value on every
  row (the harness enforces this).
- The harness forwards each row's password as the `"password"` field in the request body
  (§2).
- Passwords are held in memory only, forwarded one row at a time, and never persisted.

If your chatbot uses a single shared credential (or none), leave this **off** and handle
auth inside your connector however you like; the CSV then needs no `password` column.

---

## 8. Build & test locally before registering

**Run the bundled mock connector** to see a conformant service and to model yours on it:

```bash
harness mock-connector --port 8900
# → mock connector listening on http://127.0.0.1:8900 (mode=ok)
```

It implements exactly the protocol above. Point a curl at it (or your own service) to
confirm the shape:

```bash
curl -s -X POST http://localhost:8900 \
  -H "Content-Type: application/json" \
  -d '{"testId":"t1","utteranceText":"hello"}' | jq .
```

You should get back a valid Standard Evaluation Contract. Validate your own connector's
output against §3 the same way. (The mock also supports failure modes —
`--mode status500`, `nonconformant`, `slow` — useful for seeing how the harness records
each error stage.)

---

## 9. Registering your connector in the harness

Connectors are registered through the **Connector Registry** UI — there is no code
change in the harness to add one. Open the registry, choose **Register new connector**,
and provide the metadata:

| Field | Required | Notes |
|---|---|---|
| **Display name** | Yes | Human-readable label shown in the job wizard, dashboard, detail view, and exports. This exact name is snapshotted onto each job at creation time. |
| **Description** | No | Free text. |
| **Endpoint URL** | Yes | Full `http://` or `https://` URL the harness will `POST` to. |
| **Auth mode** | Yes | `none` / `bearer` / `api-key-header` / `basic` / `client-credentials` (§6). For the non-`none` modes you also enter the credential (token / header name + value / username + password). For `client-credentials` you enter a **token URL**, **client ID**, **client secret**, and optional **scope** + **audience**; only the client secret is stored encrypted. |
| **Timeout (seconds)** | Yes | 1–300, default 30. The harness aborts a row's call after this. |
| **Expects per-row password** | Yes (toggle) | Enable only if your chatbot needs a per-row credential (§7). |

**Test connection.** The registration form has a *Test connection* button that sends a
sample request to your endpoint and reports whether the response is a conformant
contract — use it to confirm your service before saving.

**After registering:**

- The credential is encrypted at rest immediately.
- Testers select your connector by **display name** in the job wizard. At job creation
  the full configuration (URL, auth, timeout, per-row-password flag) is **snapshotted**
  onto the job — later edits to the registration do **not** change existing jobs.
- You can **edit** the registration (rotate the credential, change the timeout, etc.),
  **archive** it (hides it from new jobs while preserving historical ones), or
  **restore** it. A registration referenced by historical jobs cannot be hard-deleted.

---

## 10. Requirements checklist

Your connector is ready to register when it:

- [ ] Accepts `POST` with a JSON body `{testId, utteranceText, password?}`.
- [ ] Returns HTTP **`200`** on success.
- [ ] Returns a body matching the Standard Evaluation Contract (§3): all top-level
      required fields, `contractVersion: "1"`, `conversationContext: null`, and a
      `chatbotResponse` with `rawPayload` / `normalizedText` / `agentChain` / `metadata`.
- [ ] Generates a unique `utteranceId` per response and echoes `testId` + `utteranceText`.
- [ ] Responds within the timeout you'll register (no long polling; the harness won't retry).
- [ ] Never includes the per-row `password` in its response.
- [ ] Enforces whatever auth mode you'll register (or `none`).
- [ ] Is reachable from the harness host at the URL you'll register.

---

## 11. Live Chat mode — SSE connector protocol

When a connector is registered with the **Supports live chat** toggle enabled, testers can
select it in the **Chat Sessions** wizard. In this mode the harness streams turns one-by-one
through your connector instead of batching the whole CSV.

### What changes in SSE mode

The harness sends the **same HTTP `POST`** to your `endpointUrl`, but:

- The **request body** uses a different shape (see below).
- You must respond with **`Content-Type: text/event-stream`** (Server-Sent Events) instead
  of a single JSON object.
- You stream **token events** as the chatbot replies, followed by a single **contract event**
  containing the completed Standard Evaluation Contract.

### Request the harness sends (SSE mode)

```json
{
  "auth": {
    "test_id": "hours-001",
    "password": "hunter2"
  },
  "message": "What are your opening hours?"
}
```

| Field | Notes |
|---|---|
| `auth.test_id` | The test ID configured at chat session creation. |
| `auth.password` | The password configured at session creation (empty string if not set). |
| `message` | The user's chat message for this turn. |

### Response you must return (SSE stream)

Return HTTP **`200`** with `Content-Type: text/event-stream`. Send events in this order:

**1 — Zero or more `token` events** (streaming chunks of the chatbot's reply):

```
event: token
data: {"content": "We're open "}

event: token
data: {"content": "9 to 5, Monday through Friday."}

```

**2 — Exactly one `contract` event** (the completed Standard Evaluation Contract — same schema as §3):

```
event: contract
data: {"contractVersion":"1","utteranceId":"a3f1...","utteranceText":"What are your opening hours?","testId":"hours-001","conversationContext":null,"connectorId":"acme-support-bot","timestamp":"2026-06-05T14:32:00Z","chatbotResponse":{"rawPayload":{},"normalizedText":"We're open 9 to 5, Monday through Friday.","agentChain":[],"metadata":{}}}

```

The harness streams `token` events live to the tester's browser. After receiving the `contract`
event it closes the SSE connection and proceeds to the evaluator. **The `contract` event must be
the last event you emit.**

Set `utteranceText` to the `message` from the request and `testId` to `auth.test_id`.

### SSE error stages

| Stage | When it happens |
|---|---|
| `connector_stream` | Harness could not connect, received HTTP non-2xx, or the stream stalled for longer than `timeoutSeconds` without a new chunk |
| `connector_normalization` | The `contract` event data was not valid JSON or failed Standard Evaluation Contract validation (§3) |

### Reference SSE connector (Python / FastAPI)

```python
import asyncio
import json
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.post("/sse-connect")
async def sse_connect(body: dict):
    test_id = body["auth"]["test_id"]
    password = body["auth"].get("password", "")
    message = body["message"]

    async def event_stream():
        reply = await call_my_chatbot(message, password)   # <- your integration
        # Stream reply as tokens
        for word in reply.split():
            chunk = word + " "
            yield f"event: token\ndata: {json.dumps({'content': chunk})}\n\n"
            await asyncio.sleep(0)
        # Finish with the full contract
        contract = {
            "contractVersion": "1",
            "utteranceId": str(uuid.uuid4()),
            "utteranceText": message,
            "testId": test_id,
            "conversationContext": None,
            "connectorId": "acme-support-bot",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "chatbotResponse": {
                "rawPayload": {"text": reply},
                "normalizedText": reply,
                "agentChain": [],
                "metadata": {},
            },
        }
        yield f"event: contract\ndata: {json.dumps(contract)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**Registering an SSE connector.** In the Connector Registry, toggle **Supports live chat** on
before saving. Only connectors with this flag appear in the Chat Sessions wizard. All other
registration fields (auth mode, timeout, credentials) work identically to the batch mode.

---

## Appendix — field quick reference

**Request → connector:** `testId`, `utteranceText`, `password?`

**Connector → harness (Standard Evaluation Contract):**
`contractVersion`(="1"), `utteranceId`, `utteranceText`, `testId`,
`conversationContext`(=null), `connectorId`, `timestamp`,
`chatbotResponse`{ `rawPayload`, `normalizedText`, `agentChain`, `metadata` },
`tokenUsage?`{ `promptTokens?`, `completionTokens?`, `totalTokens?` }

**Connector error stages:** `connector_transport`, `connector_response`,
`connector_normalization`, `connector_auth`
