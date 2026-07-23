# Building an Evaluation Agent — Developer Guide

This guide is for developers building an **evaluation agent** (an "evaluator"): an HTTP
service that scores a chatbot's response. You deploy it in your own environment, then
register it in the harness by entering its metadata (URL, auth, timeout, scoring
dimensions). This document covers the request the harness sends you, the result shape
you must return, the validation and error categories you'll be graded against, scoring
dimensions, and the registration steps.

> It is the mirror image of the **connector** guide. Read that one too — the request the
> harness sends *you* is the very contract a connector *produced*.

---

## 1. What an evaluator is

After a connector turns a chatbot's reply into a **Standard Evaluation Contract**, the
harness makes **one HTTP `POST`** to your evaluator with that contract as the body. Your
evaluator inspects the utterance + the chatbot's response and returns an
**EvaluationResult**: a verdict plus per-dimension scores. The harness validates and
persists that result.

```
connector ──Standard Evaluation Contract──▶ harness ──POST (same contract)──▶ YOUR EVALUATOR
harness ◀──────────── EvaluationResult (JSON) ───────────────────────────────┘
```

Key idea: **the connector's output and your evaluator's input are the same shape** (the
Standard Evaluation Contract). **Your output is a different shape** (the EvaluationResult).
Your evaluator is stateless from the harness's point of view — every row is an independent
request; there is no session.

Your evaluator may be non-deterministic (e.g. an LLM judge). The harness never caches or
deduplicates — every call is fresh.

---

## 2. The request the harness sends you — the Standard Evaluation Contract

| Aspect | Value |
|---|---|
| Method | `POST` |
| URL | Your registered `endpointUrl` (called verbatim for every row) |
| `Content-Type` | `application/json` |
| Auth header | Added by the harness per your registered auth mode (see §6) |
| Body | A **Standard Evaluation Contract** instance (the connector's output, unchanged) |
| Timeout | The harness aborts the call after your registered `timeoutSeconds`; it does **not** retry |

The body is the full contract. The fields you'll typically read:

| Field | Why you care |
|---|---|
| `utteranceId` | **You must echo this back** in your result — it's the correlation key (see §3). |
| `utteranceText` | The original user input being tested. |
| `testId` | The test-case id (for your own logging/grouping if useful). |
| `chatbotResponse.normalizedText` | The chatbot's reply as plain text — usually what you score. |
| `chatbotResponse.rawPayload` | The raw chatbot response, if you need structure beyond the text. |
| `chatbotResponse.agentChain` / `.metadata` | Optional signal (agents invoked, latency, etc.). |
| `conversationContext` | `null` in v1; don't depend on its shape. |
| `tokenUsage` | LLM token counts from the connector call, if reported. Present only when the connector included it; absent for non-LLM connectors. Read this if your evaluator logic accounts for token costs. |

The full contract schema (every field + types) is documented in the **connector developer
guide** — the connector produces it, you consume it. Treat unknown fields leniently; the
contract is additive.

---

## 3. The response you must return — EvaluationResult

Return HTTP **`200`** with a JSON object containing **all** of the following fields. (This
shape is validated programmatically by the harness, not by the contract schema — it is a
*different* shape from the contract.)

| Field | Type | Rules |
|---|---|---|
| `utteranceId` | string | **Must equal the `utteranceId` from the request contract.** A mismatch fails the row. |
| `evaluationAgentId` | string | An identifier for your evaluator. (A value that differs from the registered id is *not* an error — it's a soft signal — but echoing a stable id is recommended.) |
| `evaluationTimestamp` | string | RFC 3339 / ISO-8601 datetime, e.g. `2026-06-05T14:32:05Z`. |
| `evaluationVerdict` | string | **Exactly one of `pass` / `fail` / `warn`.** Any other value fails the row. |
| `evaluationScores` | array | Zero or more score entries; see below. `[]` is allowed. |
| `utteranceIntent` | string \| omitted | **Optional.** An intent category or label your evaluator assigns to this utterance (e.g. `"account inquiry"`, `"complaint"`). When present, the harness stores it (truncated to 255 chars) and surfaces it in the Intent Breakdown panel of the analytics dashboard. Omit the key entirely when you do not classify intents — `null` and `""` are treated the same as omission. |
| `tokenUsage` | object \| omitted | **Optional.** LLM token counts for this evaluation call; see below. Omit for non-LLM evaluators. |
| `metadata` | object | Free-form evaluator metadata (model, prompt id, …). No keys standardized. **`{}` is valid.** |

### Each `evaluationScores` entry

Two shapes are accepted. Both are valid and the harness stores them transparently.

**v1 — without per-parameter verdict:**
```json
{ "parameter_name": "relevance", "score": 0.92, "reasoning": "Directly answers the question." }
```

**v2 — with optional per-parameter verdict:**
```json
{ "parameter_name": "relevance", "score": 0.92, "verdict": "pass", "reasoning": "Directly answers the question." }
```

| Field | Type | Rules |
|---|---|---|
| `parameter_name` | string | The scoring dimension's name. Align these with your **declared dimensions** (§7). |
| `score` | number **or** string | A numeric score or a label (e.g. `0.92`, `4`, `"high"`). **Booleans are rejected.** |
| `verdict` | string \| omitted | **Optional.** A per-parameter verdict (e.g. `"pass"`, `"fail"`, `"warn"`). When present across entries, the analytics dashboard shows a per-parameter verdict distribution tile. When absent, that tile shows a "not available" placeholder — omitting `verdict` is not an error. You may emit it for some parameters and not others. |
| `reasoning` | string | Why this score. Empty string is allowed, but prefer a real explanation — it surfaces in the detail view and exports. |

### `tokenUsage` object (optional)

Report LLM token consumption for the evaluation call itself. Omit the key entirely for
non-LLM evaluators. All three sub-fields are optional; include whichever your LLM SDK
exposes.

| Field | Type | Notes |
|---|---|---|
| `promptTokens` | integer ≥ 0 | Tokens consumed by the prompt / input. |
| `completionTokens` | integer ≥ 0 | Tokens consumed by the completion / output. |
| `totalTokens` | integer ≥ 0 | Total tokens consumed. **The harness uses this value for per-row and job-level token aggregation.** |

The harness adds `totalTokens` from the connector and evaluator responses to produce a
**row total**, then sums row totals to produce a **job-level token count** included in
every export. A row where neither side reports `totalTokens` shows `null` rather than `0`.

### Complete example response

```json
{
  "utteranceId": "a3f1c2de-9b44-4e7a-8c11-2b6f0d9e1234",
  "evaluationAgentId": "acme-llm-judge",
  "evaluationTimestamp": "2026-06-05T14:32:05Z",
  "evaluationVerdict": "pass",
  "utteranceIntent": "account inquiry",
  "evaluationScores": [
    { "parameter_name": "relevance",    "score": 0.92, "verdict": "pass", "reasoning": "Directly answers the question." },
    { "parameter_name": "tone",         "score": "appropriate", "reasoning": "Polite and concise." },
    { "parameter_name": "groundedness", "score": 0.80, "verdict": "pass", "reasoning": "Matches the knowledge base." }
  ],
  "tokenUsage": { "promptTokens": 318, "completionTokens": 47, "totalTokens": 365 },
  "metadata": { "model": "acme-judge-v2" }
}
```

> There is **no** top-level `reasoning` field — per-score reasoning lives inside each
> `evaluationScores` entry. Do not invent a `userFeedback*` field; the harness has no
> feedback concept.
>
> Both `utteranceIntent` and per-entry `verdict` are **optional** — existing evaluators
> that omit them continue to work without any changes.

---

## 4. Reference implementation (Python/Flask sketch)

Any HTTP server in any language works:

```python
from datetime import datetime, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)
AGENT_ID = "acme-llm-judge"

@app.post("/evaluate")
def evaluate():
    contract = request.get_json(force=True)
    utterance = contract["utteranceText"]
    answer = contract["chatbotResponse"]["normalizedText"]

    verdict, scores = run_my_judge(utterance, answer)   # <- your scoring logic

    return jsonify({
        "utteranceId": contract["utteranceId"],          # echo it back
        "evaluationAgentId": AGENT_ID,
        "evaluationTimestamp": datetime.now(timezone.utc).isoformat(),
        "evaluationVerdict": verdict,                    # "pass" | "fail" | "warn"
        "evaluationScores": scores,                      # [{parameter_name, score, reasoning}, ...]
        "metadata": {},
    }), 200
```

The harness ships a **bundled mock evaluator** you can read and run as a worked reference —
see §8.

---

## 5. How the harness grades your response — error categories

The harness records one of these per-row outcomes. The four `evaluator_*` stages are the
ones your service influences.

| Stage | When it happens | How to avoid it |
|---|---|---|
| *(success)* | You returned `200` with a valid EvaluationResult | — |
| `evaluator_transport` | The harness couldn't reach you, the connection failed, or your response exceeded `timeoutSeconds` | Be reachable; respond within the timeout; the harness will **not** retry |
| `evaluator_response` | You returned a **non-2xx** HTTP status (the body is recorded, truncated, as the detail) | Return `200` |
| `evaluator_result` | You returned `2xx` but the body **isn't valid JSON** or **fails result validation** (missing/mis-typed field, verdict not in `pass`/`fail`/`warn`, `utteranceId` doesn't match the contract, bad score entry, non-ISO timestamp) | Match §3 exactly: echo `utteranceId`, use a closed-enum verdict, include all required fields with correct types |
| `evaluator_auth` | The harness couldn't obtain the service credential — either it couldn't **decrypt the stored credential** (key missing/rotated) or, for `client-credentials`, the **token request failed** (token URL unreachable, non-2xx, or no `access_token`) | Decrypt failures are a harness-side config issue (re-register the credential); token failures mean checking the token URL / client id / client secret / scope you registered |

Per-row failures are **isolated**: a failing row is recorded with its stage + detail and
the run continues. One bad row never aborts the job.

---

## 6. Authentication

Your endpoint can require auth. The harness attaches the header based on the **auth mode**
chosen at registration; you implement the matching check.

| Auth mode | Header the harness sends | You implement |
|---|---|---|
| `none` | *(none)* | Open endpoint (use network controls instead) |
| `bearer` | `Authorization: Bearer <token>` | Validate the bearer token |
| `api-key-header` | `<your-header-name>: <value>` | Validate a custom header (e.g. `X-API-Key`) |
| `basic` | `Authorization: Basic base64(user:pass)` | Validate HTTP Basic credentials |
| `client-credentials` | `Authorization: Bearer <fetched-token>` | Validate the bearer token your gateway/IdP issued |

The credential is entered once at registration and **encrypted at rest**; it is decrypted
only in memory when building each request and is never logged, exported, or shown in the
UI. (Evaluators have no per-row password concept — that's a connector-only feature.)

For `client-credentials`, the harness runs the OAuth2 **client-credentials grant** itself:
before each call it `POST`s `grant_type=client_credentials` (plus your client id, client
secret, and optional scope/audience) as a form-encoded body to your registered **token URL**,
reads `access_token` from the JSON response, and attaches it as `Authorization: Bearer <token>`.
Tokens are cached in memory and reused until shortly before `expires_in`, then re-fetched. A
failed token request records the row under `evaluator_auth` and your endpoint is never called.

---

## 7. Declared scoring dimensions

At registration you declare an **ordered list of scoring dimensions** (e.g. `relevance`,
`groundedness`, `tone`). These are metadata about what your evaluator measures, and they
shape how results are displayed — they do **not** constrain what you return at runtime:

- **Emit scores for your declared dimensions.** Their order drives the column order in the
  detail view and in exports, so results line up across rows and across jobs that used the
  same evaluator.
- **Emitting an *undeclared* `parameter_name` is allowed** — it's recorded and shown, but
  the harness flags it as a soft warning (`harnessAnnotations.unexpected_score_dimensions`)
  so the tester can see your output diverged from the registration. It does **not** fail
  the row or change the verdict.
- **Omitting a declared dimension is allowed** — downstream it simply shows as
  unevaluated (`—`) for that row. No failure.

So: declared dimensions are a contract about *intent and presentation*, not a hard runtime
gate. Keep them in sync with what you actually emit to avoid spurious "unexpected
dimension" warnings.

---

## 8. Build & test locally before registering

**Run the bundled mock evaluator** to see a conformant service:

```bash
harness mock-evaluator --port 8901 --dimensions "relevance,groundedness"
# → mock evaluator listening on http://127.0.0.1:8901 (mode=ok)
```

Send it a sample contract (it echoes `utteranceId` and returns a well-formed result):

```bash
curl -s -X POST http://localhost:8901 \
  -H "Content-Type: application/json" \
  -d '{"contractVersion":"1","utteranceId":"u-1","utteranceText":"hi","testId":"t1",
       "conversationContext":null,"connectorId":"c","timestamp":"2026-06-05T00:00:00Z",
       "chatbotResponse":{"rawPayload":{},"normalizedText":"hello","agentChain":[],"metadata":{}}}' | jq .
```

Validate your own evaluator's output against §3 the same way. The mock also supports
failure modes — `--mode status500`, `nonconformant`, `slow`, and `unexpected_dims` (emits a
dimension you didn't declare) — useful for seeing how the harness records each error stage
and the unexpected-dimension warning.

---

## 9. Registering your evaluator in the harness

Evaluators are registered through the **Evaluator Registry** UI — no harness code change.
Open the registry, choose **Register new evaluator**, and provide the metadata:

| Field | Required | Notes |
|---|---|---|
| **Display name** | Yes | Human-readable label shown in the job wizard, detail view, and exports. Snapshotted onto each job at creation time. |
| **Description** | **Yes** | What this evaluator measures / how it judges. (Required for evaluators.) |
| **Endpoint URL** | Yes | Full `http://` or `https://` URL the harness `POST`s the contract to. |
| **Auth mode** | Yes | `none` / `bearer` / `api-key-header` / `basic` / `client-credentials` (§6), plus the credential for the non-`none` modes. For `client-credentials` you enter a **token URL**, **client ID**, **client secret**, and optional **scope** + **audience**; only the client secret is stored encrypted. |
| **Timeout (seconds)** | Yes | 1–600, default 60. The harness aborts a row's call after this. (Judges are often slower than connectors — size this for your model.) |
| **Scoring dimensions** | No | One dimension name per line (ordered). Blank lines are ignored; duplicates raise a non-blocking warning; an empty list is allowed (§7). |

**Test connection.** The registration form has a *Test connection* button that sends a
sample contract to your endpoint and reports whether the response is a valid
EvaluationResult — and warns if you emitted dimensions you didn't declare. Use it to
confirm your service before saving.

**After registering:**

- The credential is encrypted at rest immediately.
- Testers select your evaluator by **display name** in the job wizard. At job creation the
  full configuration (URL, auth, timeout, declared dimensions) is **snapshotted** onto the
  job — later edits to the registration do **not** change existing jobs.
- You can **edit** (rotate credential, adjust dimensions/timeout), **archive** (hide from
  new jobs, keep historical), or **restore** the registration. One referenced by historical
  jobs cannot be hard-deleted.

---

## 10. Requirements checklist

Your evaluator is ready to register when it:

- [ ] Accepts `POST` with a Standard Evaluation Contract JSON body.
- [ ] Returns HTTP **`200`** on success.
- [ ] Returns an EvaluationResult (§3): `utteranceId` (echoed from the request),
      `evaluationAgentId`, `evaluationTimestamp` (ISO-8601), `evaluationVerdict`
      (`pass`/`fail`/`warn`), `evaluationScores` (array of `{parameter_name, score,
      reasoning}`), `metadata` (object), and optionally `tokenUsage` (§3).
- [ ] Uses a number or string `score` (never a boolean) in each score entry.
- [ ] Emits `parameter_name`s aligned with its declared dimensions (extras are warned, not
      failed).
- [ ] Responds within the timeout you'll register (no retries on the harness side).
- [ ] Enforces whatever auth mode you'll register (or `none`).
- [ ] Is reachable from the harness host at the URL you'll register.

**Additional requirements for SSE (live chat) evaluators:**

- [ ] Responds with `Content-Type: text/event-stream`.
- [ ] Ends the stream with exactly one `final` event.
- [ ] The `final` payload uses `overallVerdict` (not `evaluationVerdict`) and `parameters[]`
      (not `evaluationScores[]`), with `parameter_name` (snake_case) in each entry.
- [ ] Uses lowercase `pass`, `fail`, or `warn` for `overallVerdict`.
- [ ] Registered with **Supports live chat** toggled on in the Evaluator Registry.

---

## 11. Live Chat mode — SSE evaluator protocol

When an evaluator is registered with the **Supports live chat** toggle enabled, it can be
selected in the **Chat Sessions** wizard. In this mode the harness POSTs the Standard
Evaluation Contract to your endpoint and expects an SSE stream of evaluation events in return.

### What changes in SSE mode

The **request** is nearly identical to batch mode (§2), with one additional header:

| Aspect | Value |
|---|---|
| Method | `POST` |
| `Content-Type` | `application/json` |
| `Accept` | `text/event-stream` |
| Body | The Standard Evaluation Contract (same as batch mode) |
| Timeout | Stall-based: the harness fails the turn if no new SSE chunk arrives within `timeoutSeconds` of the previous one |

Only the **response** changes:

- Respond with **`Content-Type: text/event-stream`** (Server-Sent Events).
- Emit zero or more **intermediate events** before the final.
- End the stream with exactly one **`final`** event.

> **The SSE `final` payload uses a different shape from the batch-mode EvaluationResult.**
> The batch-mode fields `evaluationVerdict`, `evaluationScores`, and `utteranceId` are
> **not** read in SSE mode. Use `overallVerdict` and `parameters[]` instead — see below.

### Intermediate event types

Four event types are defined. Emit zero or more of any of them before `final`.

| Event type | Example payload | Purpose |
|---|---|---|
| `score_update` | `{"dimension": "relevance", "score": 0.82, "partial": true}` | Stream a partial score as it is computed |
| `warning` | `{"message": "Response contains an ambiguous claim"}` | Flag a non-fatal quality concern |
| `insight` | `{"message": "Response correctly cites source Y"}` | Surface a positive observation |
| `diagnostic` | `{"stage": "embedding", "latency_ms": 142}` | Internal evaluator timing or debug info |

Any other event type is forwarded to the browser and persisted as-is — the harness never
errors on unknown event types. This preserves forward compatibility as your evaluator evolves.

### The `final` event

The last event in the stream must have type `final`. Its JSON payload is stored verbatim as
the turn's evaluation result. The analytics engine reads `overallVerdict` and
`parameters[].parameter_name` from it — using any other key names causes analytics to
silently show no results.

**Top-level fields:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `overallVerdict` | string | **Yes** | Overall verdict for the turn. Use lowercase `pass`, `fail`, or `warn` — the harness normalises case, but lowercase matches the batch mode enum and is recommended. |
| `parameters` | array | **Yes** | Per-dimension score entries. `[]` is valid. |
| `evaluatorId` | string | No | Identifier for your evaluator (stored verbatim). |
| `evaluatorName` | string | No | Human-readable evaluator name (stored verbatim). |
| `evaluatorVersion` | string | No | Version string (stored verbatim). |
| `overallScore` | number | No | Aggregate numeric score (stored verbatim). |

**Each `parameters` entry** — same key names as the batch-mode `evaluationScores` entry:

| Field | Type | Required | Notes |
|---|---|---|---|
| `parameter_name` | string | **Yes** | Dimension name. Use snake_case — same as batch mode. Must match your declared dimensions for correct column alignment. |
| `score` | number or string | **Yes** | Numeric or label score. Booleans are rejected. |
| `reasoning` | string | **Yes** | Explanation shown in the turn detail view. |
| `verdict` | string | No | Per-parameter verdict. When present, the analytics dashboard shows a parameter verdict distribution. |

> `parameter_name` is snake_case. Do **not** use `parameterId` or `parameterName` (camelCase)
> — those keys are not read by the harness analytics engine.

### Complete example

```
event: diagnostic
data: {"stage": "start", "latency_ms": 0}

event: score_update
data: {"dimension": "relevance", "score": 0.92, "partial": false}

event: final
data: {"overallVerdict":"pass","evaluatorId":"acme-llm-judge","parameters":[{"parameter_name":"relevance","score":0.92,"verdict":"pass","reasoning":"Directly answers the question."},{"parameter_name":"groundedness","score":0.85,"verdict":"pass","reasoning":"Matches the knowledge base."}]}

```

### SSE error stages

| Stage | When it happens |
|---|---|
| `evaluator_stream` | Harness could not connect, received HTTP non-2xx, stream closed before `final`, or no new chunk arrived within `timeoutSeconds` |

Validation errors on the `final` payload (wrong verdict value, malformed JSON) are recorded
under the existing `evaluator_result` stage.

### Reference SSE evaluator (Python / FastAPI)

```python
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()
AGENT_ID = "acme-llm-judge"

@app.post("/sse-evaluate")
async def sse_evaluate(contract: dict):
    utterance = contract["utteranceText"]
    answer = contract["chatbotResponse"]["normalizedText"]

    async def event_stream():
        # Optional: emit intermediate events
        yield f"event: diagnostic\ndata: {json.dumps({'stage': 'start'})}\n\n"

        verdict, scores = await run_my_judge(utterance, answer)
        # verdict: "pass" | "fail" | "warn"
        # scores: [{"parameter_name": "...", "score": 0.9, "verdict": "pass", "reasoning": "..."}, ...]

        result = {
            "overallVerdict": verdict,   # NOT evaluationVerdict
            "evaluatorId": AGENT_ID,
            "parameters": scores,        # uses parameter_name — NOT evaluationScores
        }
        yield f"event: final\ndata: {json.dumps(result)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**Registering an SSE evaluator.** In the Evaluator Registry, toggle **Supports live chat** on
before saving. Only evaluators with this flag appear in the Chat Sessions wizard. All other
registration fields (auth mode, timeout, dimensions, credentials) work identically to batch mode.

---

## Appendix — field quick reference

**Request → evaluator (both modes):** a Standard Evaluation Contract
(`utteranceId`, `utteranceText`, `testId`, `chatbotResponse{rawPayload, normalizedText,
agentChain, metadata}`, `conversationContext`, `connectorId`, `timestamp`,
`contractVersion`). SSE mode additionally sends `Accept: text/event-stream`.

**Batch mode — evaluator → harness (EvaluationResult):**
`utteranceId` (echoed), `evaluationAgentId`, `evaluationTimestamp` (ISO-8601),
`evaluationVerdict` (`pass`|`fail`|`warn`), `evaluationScores`
[`{parameter_name, score, reasoning, verdict?}`], `utteranceIntent?` (optional intent label,
≤ 255 chars), `tokenUsage?`{ `promptTokens?`, `completionTokens?`, `totalTokens?` },
`metadata`.

**SSE mode — `final` event payload:**
`overallVerdict` (`pass`|`fail`|`warn`), `parameters`
[`{parameter_name, score, reasoning, verdict?}`], plus optional `evaluatorId`,
`evaluatorName`, `evaluatorVersion`, `overallScore`. Note: `overallVerdict`/`parameters`
are **different key names** from the batch-mode `evaluationVerdict`/`evaluationScores`.
The `parameter_name` key inside each entry is identical in both modes.

**SSE intermediate event types:** `score_update`, `warning`, `insight`, `diagnostic`.
Unknown types are forwarded and persisted without error.

**Evaluator error stages (batch):** `evaluator_transport`, `evaluator_response`,
`evaluator_result`, `evaluator_auth`.

**Evaluator error stage (SSE):** `evaluator_stream` (connection failure, non-2xx, stall
timeout, or stream closed before `final`). Malformed `final` payload → `evaluator_result`.
