# Research: Live Chat & Real-Time Evaluation

**Feature**: 017-live-chat-evaluation | **Date**: 2026-06-22

---

## 1. SSE Server Infrastructure

**Decision**: FastAPI `StreamingResponse` + async generator + per-turn `asyncio.Condition`-based in-memory event bus.

**Rationale**: The app runs under UvicornWorker (ASGI), so the asyncio event loop is already active. A per-turn bus backed by a shared `list[str]` and an `asyncio.Condition` supports both live streaming (reader blocks until new events arrive) and reconnect replay (reader rewinds cursor to 0 and replays from the buffer). No external message broker is needed for a single-server deployment serving 50–80 users.

**Alternatives considered**:
- `asyncio.Queue` — does not support replay (consumed events are gone); rejected.
- Redis pub/sub — viable for multi-server horizontal scale, but over-engineered for the deployment target; rejected.
- `asyncio.Event` with a single flag — does not support cursor-based replay; rejected.

**Implementation sketch**:
```python
class TurnEventBus:
    events: list[str]            # raw SSE strings, append-only
    _condition: asyncio.Condition
    _complete: bool

    async def publish(self, event: str) -> None: ...
    async def mark_complete(self) -> None: ...
    async def stream_from(self, cursor: int = 0):  # async generator
        while True:
            async with self._condition:
                while cursor >= len(self.events) and not self._complete:
                    await self._condition.wait()
                while cursor < len(self.events):
                    yield self.events[cursor]; cursor += 1
                if self._complete: return
```

---

## 2. Mixed Sync/Async FastAPI Routes

**Decision**: New chat routes (SSE endpoints, turn submission, session CRUD, wizard) are `async def`; all existing routes stay `def` (sync, run in thread pool by FastAPI).

**Rationale**: FastAPI natively mixes sync and async handlers on the same app. Async is required for SSE and the connector/evaluator pipeline (blocking I/O on httpx streams must not block the event loop). Existing sync routes are unaffected.

**Background task**: Connector→evaluator pipeline is launched via FastAPI `BackgroundTasks` on the turn-submission POST, so the response (returning the `turn_id`) is returned immediately before streaming begins.

---

## 3. Async HTTP Streaming (httpx)

**Decision**: `httpx.AsyncClient` with `client.stream("POST", url, ...)` + `aiter_lines()` for both connector and evaluator calls.

**Rationale**: httpx ≥ 0.27 is already in `pyproject.toml`. `aiter_lines()` gives clean line-by-line SSE parsing. Stall detection wraps each `__anext__()` call with `asyncio.wait_for(..., timeout=snapshotted_timeout_seconds)`.

**SSE line parsing**: Standard SSE wire format: lines starting with `data:` contain the JSON payload; lines starting with `event:` name the event type; blank lines delimit events.

**Stall timeout**:
```python
try:
    line = await asyncio.wait_for(stream.__anext__(), timeout=timeout_seconds)
except asyncio.TimeoutError:
    raise ConnectorStreamError("Stall timeout exceeded")
```

---

## 4. GFM Client-Side Rendering

**Decision**: marked.js v14 via jsDelivr CDN, configured with `{ gfm: true, breaks: false }`.

**Rationale**: marked.js is the most widely deployed standalone GFM renderer with no bundler requirement. v14 supports all required GFM constructs: CommonMark base, tables, fenced code blocks, strikethrough, task lists. Loading from CDN requires one `<script>` tag — compatible with the project's no-bundler constraint.

**CDN tag** (to be pinned to minor version for stability):
```html
<script src="https://cdn.jsdelivr.net/npm/marked@14/marked.min.js"></script>
```

**Render call**:
```javascript
const html = marked.parse(assembledBuffer, { gfm: true, breaks: false });
```

**Alternatives considered**:
- showdown.js — older codebase, weaker GFM compliance; rejected.
- micromark — no ready-made browser bundle without a bundler; rejected.
- highlight.js for code block syntax highlighting — out of scope for this release; noted for future enhancement.

---

## 5. HTML Sanitization (DOMPurify)

**Decision**: DOMPurify v3 via jsDelivr CDN, applied after every marked.js render call.

**Rationale**: DOMPurify is the browser security standard for sanitizing HTML before DOM insertion. Default configuration strips `<script>`, `on*` event handler attributes, `javascript:` URL schemes, `<iframe>`, `<object>`, `<embed>`, and other active-content vectors. Safe structural and presentational markup produced by marked.js is preserved. Must run on every render pass — including incremental streaming renders.

**CDN tag**:
```html
<script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
```

**Render pipeline**:
```javascript
function renderGfm(text) {
    const raw = marked.parse(text, { gfm: true, breaks: false });
    return DOMPurify.sanitize(raw);
}
// On each token arrival:
element.innerHTML = renderGfm(assembledBuffer);
```

---

## 6. Streaming-Aware Markdown Rendering

**Decision**: Re-render the full assembled buffer on each token arrival. marked.js renders partial Markdown constructs as literal text until the closing delimiter arrives; this is acceptable — a partial code fence briefly appears as backticks in plain text, then snaps to a rendered block when the closing ` ``` ` arrives.

**Rationale**: Full-buffer re-render on each token is simple, robust, and correct. The alternative (incremental AST diffing) requires a bundler and is not worth the complexity at this scale.

**Tester messages**: Always rendered as `textContent` (plain text), never passed through marked/DOMPurify.

---

## 7. Password Reveal Toggle

**Decision**: Standard HTML `<input type="password">` in wizard step 3 with an adjacent button that toggles the `type` attribute between `"password"` and `"text"`. Reveal toggle present only in the wizard; read-only chat view uses `<input type="password" readonly disabled>` with no toggle.

**Rationale**: Native browser implementation — no library needed. The toggle is a one-line JS function.

```javascript
function toggleReveal(inputId, btn) {
    const inp = document.getElementById(inputId);
    const showing = inp.type === 'text';
    inp.type = showing ? 'password' : 'text';
    btn.textContent = showing ? 'Show' : 'Hide';
}
```

---

## 8. Credential Encryption

**Decision**: Reuse `harness.persistence.encryption.encrypt_credential` / `decrypt_credential` (Fernet, AES-128-CBC + HMAC). Store `test_id` and `password` in separate `Text` columns (`test_id_enc`, `test_password_enc`) on `ChatSession`. Decrypt server-side only when building the connector request body per turn.

**Rationale**: Identical pattern to existing `auth_descriptor` credential-subfield encryption. Keeps a single encryption boundary (Fernet, existing key management).

---

## 9. Server-Startup Recovery

**Decision**: During the FastAPI `lifespan` startup hook (after migrations), query all `ChatTurn` rows with `status = "in_progress"` and bulk-update them to `status = "failed"` with `error_details = "Server restarted while turn was in progress"`. The in-memory event bus registry is empty on startup — no bus cleanup needed.

**Rationale**: Per FR-LC-051. Mirrors the pattern where `Job` rows in `running` status are recovered on startup in the existing `bootstrap.py`.

---

## 10. Admin Inactivity Calculation

**Decision**: Inactivity date = `MAX(chat_turn.created_at)` for sessions with at least one turn; `chat_session.created_at` for sessions with zero turns (per FR-LC-019).

**Implementation**: Bulk-delete query uses a single SQL subquery or LEFT JOIN to compute the effective last-activity date for each session, then filters by the selected window.

---

## 11. Concurrent In-Progress Turn Guard

**Decision**: Server-side check on turn submission: if any `ChatTurn` for the session has `status = "in_progress"`, reject the new submission with HTTP 409. No client-side locking needed.

**Rationale**: Per FR-LC-050. SQLite serialises writes — the check-then-insert is safe within a transaction.
