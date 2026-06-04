# Quickstart: Connector Framework (Module 4)

**Date**: 2026-06-04
**Plan**: `specs/007-connector-framework/plan.md`

End-to-end verification, organized by user story. Built on `foundation` (010+009+006). Automated test is canonical; the mock-service path supports manual exercise.

---

## Prerequisites

- `pip install -e .[dev]` (adds `httpx`).
- `foundation` code present (registry/encryption from `009`, `validate_contract` from `006`).

---

## US1 + US4: Dispatch a row through the bundled mock connector

### Automated (canonical)

```bash
pytest tests/integration/test_connector_e2e.py -v
pytest tests/integration/test_mock_service.py -v
```

### Manual

```bash
# 1. Launch the bundled mock connector on a port (auth none):
harness mock-connector --port 9009
# 2. In another shell, dispatch a row at it:
python - <<'EOF'
import httpx
from harness.connector import dispatch_utterance, ConnectorSnapshot, UtteranceRow
snap = ConnectorSnapshot(connector_id="mock", endpoint_url="http://127.0.0.1:9009",
                         auth_descriptor={"mode":"none"}, timeout_seconds=10,
                         expects_per_row_password=False)
r = dispatch_utterance(snap, UtteranceRow(test_id="t1", utterance_text="hello"))
print("ok:", r.ok, "stage:", r.error_stage, "connectorId:", (r.contract or {}).get("connectorId"))
EOF
# Expected: ok: True  stage: None  connectorId: mock
```

---

## US2: Add a connector with zero core changes

### Automated (canonical)

```bash
pytest tests/integration/test_connector_e2e.py::test_register_and_run_mock_no_core_change -v
```

Registers the mock's URL via `009`'s `ConnectorRegistrationRepository`, lists it through `ConnectorRegistryReader.list_active()`, and dispatches against it — no source-tree change.

---

## US3: Credentials protected at rest + just-in-time

### Automated (canonical)

```bash
pytest tests/unit/connector/test_client.py -k "auth or decrypt" -v
pytest tests/unit/connector/test_auth.py -v
```

Covers: the 4 auth modes build the right header (FR-007a-d); a registration credential is stored as ciphertext (reuses `009`); a decrypt failure → `connector_auth` (FR-016). The deeper at-rest grep checks live in `009`'s `test_encryption.py` (SC-004/005).

---

## US-wide: error-stage mapping via the mock's modes

```bash
# non-2xx → connector_response
harness mock-connector --port 9009 --mode status500
# 2xx invalid body → connector_normalization
harness mock-connector --port 9009 --mode nonconformant
# sleep past timeout → connector_transport
harness mock-connector --port 9009 --mode slow
```

Dispatch against each and confirm `r.error_stage` matches the table (FR-006; SC-008/009/010).

---

## Pass criteria

```bash
pytest tests/unit/connector tests/integration/test_connector_e2e.py tests/integration/test_mock_service.py -v
ruff check src tests
```

All four user stories verified; exactly one HTTP request per row; failures categorized to the four connector error stages; credentials never in plaintext at rest; the mock runs with zero external setup.
