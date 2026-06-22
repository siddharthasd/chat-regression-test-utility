# Data Model: Live Chat & Real-Time Evaluation

**Feature**: 017-live-chat-evaluation | **Date**: 2026-06-22

---

## Migration

**File**: `src/harness/persistence/migrations/versions/0005_add_live_chat.py`

**Changes**:
1. `ALTER TABLE connector_registration ADD COLUMN supports_sse BOOLEAN NOT NULL DEFAULT 0`
2. `ALTER TABLE evaluation_agent_registration ADD COLUMN supports_sse BOOLEAN NOT NULL DEFAULT 0`
3. `CREATE TABLE chat_session (...)`
4. `CREATE TABLE chat_turn (...)`
5. `CREATE TABLE chat_turn_result (...)`
6. `CREATE TABLE evaluation_event (...)`

Existing `ConnectorRegistration` and `EvaluationAgentRegistration` rows default to `supports_sse = False` (backward-compatible).

---

## Existing Models: Changes

### ConnectorRegistration (`connector_registration.py`)

Add one field:

```python
supports_sse: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

### EvaluationAgentRegistration (`evaluator_registration.py`)

Add one field:

```python
supports_sse: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

---

## New Models

### ChatSession (`chat_session.py`)

Represents one named live testing session. Created once; all fields except `turns` are immutable after creation.

```python
class ChatSession(Base):
    __tablename__ = "chat_session"

    chat_session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_oid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Test credentials — Fernet-encrypted at rest
    test_id_enc: Mapped[str] = mapped_column(Text, nullable=False)
    test_password_enc: Mapped[str] = mapped_column(Text, nullable=False)

    # Connector snapshot (immutable; set at creation from ConnectorRegistration)
    connector_id: Mapped[str | None] = mapped_column(String(36))
    connector_name: Mapped[str | None] = mapped_column(String(255))
    connector_endpoint_url: Mapped[str | None] = mapped_column(Text)
    connector_auth_descriptor: Mapped[dict | None] = mapped_column(JSON)
    connector_timeout_seconds: Mapped[int | None] = mapped_column(Integer)

    # Evaluator snapshot (immutable; set at creation from EvaluationAgentRegistration)
    evaluator_id: Mapped[str | None] = mapped_column(String(36))
    evaluator_name: Mapped[str | None] = mapped_column(String(255))
    evaluator_endpoint_url: Mapped[str | None] = mapped_column(Text)
    evaluator_auth_descriptor: Mapped[dict | None] = mapped_column(JSON)
    evaluator_timeout_seconds: Mapped[int | None] = mapped_column(Integer)
    evaluator_declared_scoring_dimensions: Mapped[list | None] = mapped_column(JSON)

    turns: Mapped[list["ChatTurn"]] = relationship(
        cascade="all, delete-orphan",
        order_by="ChatTurn.created_at",
        lazy="select",
    )
```

**Field notes**:
- `owner_oid`: Azure AD OID of the creating user; scopes visibility to the owner (admins can see all).
- `test_id_enc` / `test_password_enc`: output of `encrypt_credential(plaintext)`. Never exposed in plain text after creation.
- `connector_auth_descriptor` / `evaluator_auth_descriptor`: JSON dict; credential subfields within are themselves encrypted (same convention as `Job` snapshots).
- There is no `status` column — sessions are always "active" from creation until deleted. Lifecycle is expressed through deletion, not a state field.

---

### ChatTurn (`chat_turn.py`)

Represents one user message within a session.

```python
class ChatTurn(Base):
    __tablename__ = "chat_turn"

    turn_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_session.chat_session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="in_progress"
    )  # in_progress | completed | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    result: Mapped["ChatTurnResult | None"] = relationship(
        uselist=False, cascade="all, delete-orphan", lazy="select"
    )
    evaluation_events: Mapped[list["EvaluationEvent"]] = relationship(
        cascade="all, delete-orphan",
        order_by="EvaluationEvent.sequence_number",
        lazy="select",
    )
```

**State transitions**: `in_progress → completed | failed`

**Startup recovery**: At server startup, any `ChatTurn` with `status = "in_progress"` is updated to `status = "failed"` and a `ChatTurnResult` is written with `error_stage = "server_restart"`.

---

### ChatTurnResult (`chat_turn_result.py`)

The assembled output for one completed or failed turn. One-to-one with `ChatTurn`; written in a single batch at turn end.

```python
class ChatTurnResult(Base):
    __tablename__ = "chat_turn_result"

    turn_result_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_turn.turn_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    assembled_response: Mapped[str | None] = mapped_column(Text)
    normalized_contract: Mapped[dict | None] = mapped_column(JSON)
    final_evaluation_result: Mapped[dict | None] = mapped_column(JSON)
    error_stage: Mapped[str | None] = mapped_column(String(50))
    # error_stage values: connector_stream | connector_normalization |
    #                     evaluator_stream | server_restart
    error_details: Mapped[str | None] = mapped_column(Text)
```

**Field notes**:
- `assembled_response`: concatenation of all `token` event content strings from the connector.
- `normalized_contract`: the Standard Evaluation Contract extracted from the connector's `contract` event payload.
- `final_evaluation_result`: populated from the evaluator's `final` event payload (the complete `EvaluationResult`). `None` if evaluation did not complete.
- `error_stage`: set on failure; `None` on `completed` turns. Also written on `server_restart`.
- `assembled_response` may be partially filled on failure (whatever was buffered before the error).

---

### EvaluationEvent (`evaluation_event.py`)

One structured event emitted by the evaluator during a turn. Written in batch at turn end; ordered by `sequence_number`.

```python
class EvaluationEvent(Base):
    __tablename__ = "evaluation_event"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_turn.turn_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Known types: score_update | warning | insight | diagnostic | final
    # Unknown types: persisted as-is with raw type string
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

---

## Relationships

```text
ChatSession (1) ──< ChatTurn (1) ──── ChatTurnResult
                              (1) ──< EvaluationEvent[]
```

- `ChatSession` → `ChatTurn`: one-to-many; cascade delete
- `ChatTurn` → `ChatTurnResult`: one-to-one; cascade delete
- `ChatTurn` → `EvaluationEvent`: one-to-many; ordered by `sequence_number`; cascade delete

---

## Repository: ChatSessionRepository

**File**: `src/harness/persistence/repositories/chat_session_repository.py`

Key operations:

| Method | Description |
|--------|-------------|
| `create_session(session: ChatSession)` | Persist new session |
| `get_session(session_id, owner_oid)` | Fetch by ID + owner (admin: omit owner filter) |
| `list_sessions_for_owner(owner_oid)` | All sessions for a user, newest first |
| `list_all_sessions()` | Admin — all users' sessions |
| `delete_session(session_id)` | Cascade-delete session + turns + results + events |
| `create_turn(turn: ChatTurn)` | Persist new in-progress turn |
| `get_turn(turn_id, session_id)` | Fetch turn by ID + session |
| `get_in_progress_turn(session_id)` | Return the single in-progress turn if any |
| `complete_turn(turn_id, result, events)` | Batch write: update turn status + write result + events |
| `fail_turn(turn_id, result)` | Batch write: update turn status=failed + write result |
| `recover_stale_turns()` | Startup recovery: flip all in_progress → failed |
| `count_sessions_inactive_since(cutoff_dt)` | Admin stats |
| `delete_sessions_inactive_since(cutoff_dt)` | Admin bulk-delete (skips in-progress sessions) |
