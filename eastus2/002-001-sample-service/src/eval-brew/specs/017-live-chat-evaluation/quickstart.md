# Developer Quickstart: Live Chat & Real-Time Evaluation

**Feature**: 017-live-chat-evaluation

---

## Prerequisites

- Python 3.11 environment with `harness` installed (`pip install -e ".[dev]"`)
- Harness encryption key present (auto-created on first run at `%LOCALAPPDATA%\harness\master.key`)
- At least one `ConnectorRegistration` with `supports_sse = True` and one `EvaluationAgentRegistration` with `supports_sse = True`

---

## 1. Run the Migration

```bash
python -m harness.cli.serve --migrate-only
# or simply start the server; migrations run automatically on startup
```

Migration 0005 adds the 4 chat tables and the `supports_sse` columns. Verify:

```bash
python -c "
from harness.persistence.engine import get_engine
from sqlalchemy import inspect
i = inspect(get_engine())
print(i.get_table_names())
"
# Should include: chat_session, chat_turn, chat_turn_result, evaluation_event
```

---

## 2. Enable SSE on a Connector or Evaluator

Via the UI (Connector Registry → Edit) or directly in the DB for testing:

```python
from harness.persistence.engine import SessionLocal
from harness.persistence.models.connector_registration import ConnectorRegistration

with SessionLocal() as db:
    conn = db.query(ConnectorRegistration).first()
    conn.supports_sse = True
    db.commit()
```

---

## 3. Write a Mock SSE Connector

The easiest way to test the feature without a real chatbot is a minimal FastAPI mock:

```python
# mock_connector.py
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio, json

app = FastAPI()

@app.post("/chat")
async def chat(body: dict):
    async def events():
        for word in ["Hello, ", "this ", "is ", "the ", "chatbot."]:
            yield f"event: token\ndata: {json.dumps({'content': word})}\n\n"
            await asyncio.sleep(0.1)
        contract = {
            "utterance": body["message"],
            "chatbotResponse": "Hello, this is the chatbot.",
            "evaluationScores": []
        }
        yield f"event: contract\ndata: {json.dumps(contract)}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")

# Run with: uvicorn mock_connector:app --port 8001
```

Register this connector at `http://localhost:8001/chat` with `supports_sse = True`.

---

## 4. Write a Mock SSE Evaluator

```python
# mock_evaluator.py
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio, json

app = FastAPI()

@app.post("/evaluate")
async def evaluate(body: dict):
    async def events():
        yield f"event: score_update\ndata: {json.dumps({'dimension': 'relevance', 'score': 0.9})}\n\n"
        await asyncio.sleep(0.2)
        final = {"overallScore": 0.9, "passed": True, "summary": "Good response."}
        yield f"event: final\ndata: {json.dumps(final)}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")

# Run with: uvicorn mock_evaluator:app --port 8002
```

Register this evaluator at `http://localhost:8002/evaluate` with `supports_sse = True`.

---

## 5. Start the Harness

```bash
python -m harness.cli.serve
```

Navigate to `http://localhost:8080` and log in.

---

## 6. Create a Chat Session

1. Click **New Chat Session** on the dashboard.
2. Step 1 — Enter a session name (e.g. "Dev Test Session").
3. Step 2 — Select the mock connector.
4. Step 3 — Enter any test ID (e.g. `user001`) and password (e.g. `pass123`). Use the reveal toggle to verify.
5. Step 4 — Select the mock evaluator.
6. Step 5 — Confirm. You'll land on the chat interface.

---

## 7. Send a Message

Type a message and press **Send**. Observe:
- Left pane: connector tokens stream in progressively with GFM rendering.
- Left pane sticky banner: disclaimer about formatting differences vs. the real chatbot.
- Right pane: "Evaluating…" indicator, then `score_update` and `final` events.
- Both panes: session persists and UI reflects turn status.

---

## 8. Test Reconnect Replay

While a turn is streaming, open a new tab to the same session URL. Observe the new tab replays all events buffered so far and then catches up live.

---

## 9. Export

From the chat interface, click **Export JSON** or **Export CSV**. Verify the downloaded file contains the completed turn with `assembled_response`, `evaluation_events`, and `final_evaluation_result`.

---

## Key Test Fixtures

The integration tests use the existing in-memory SQLite fixture (`_isolate_harness_paths`) plus new mock connector/evaluator fixtures in `tests/integration/conftest.py`. No network calls are made in tests — mock SSE streams are injected via `httpx.MockTransport`.

```python
# tests/integration/conftest.py (addition)
@pytest.fixture
def mock_sse_connector():
    """Returns an httpx MockTransport that yields token + contract events."""
    ...

@pytest.fixture
def mock_sse_evaluator():
    """Returns an httpx MockTransport that yields score_update + final events."""
    ...
```
