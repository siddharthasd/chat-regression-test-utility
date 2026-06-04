# Quickstart: Connector Registry & Management (Module 13)

**Date**: 2026-06-04
**Plan**: `specs/013-connector-registry-management/plan.md`

End-to-end verification, organized by user story. Built on `foundation`. Automated tests use Flask's test client; the manual path uses the running UI + the bundled mock connector (007).

---

## Prerequisites

- `pip install -e .[dev]` (no new deps beyond `foundation`).
- For the manual path: a bundled mock connector running — `harness mock-connector --port 9009`.

---

## US1 + US4: Register and list connectors

### Automated (canonical)

```bash
pytest tests/integration/test_connector_registry_ui.py -v
pytest tests/unit/connector_registry -v
```

### Manual

```bash
harness serve            # open http://127.0.0.1:5000/connectors
# Click "Register new connector"; fill: name="Mock", endpoint=http://127.0.0.1:9009,
#   auth mode=none, timeout=30, expects-per-row-password=off; Save.
# Verify it appears in the active list; toggle filter Active/Archived/All; search by substring.
```

---

## US2: Edit (credential rotation, snapshot isolation)

```bash
pytest tests/unit/connector_registry/test_service.py -k "update or preserve or mode_change" -v
```

Covers: editing fields bumps `updated_at`; "Replace credential" re-encrypts; an untouched credential keeps its ciphertext (FR-012); changing auth mode discards the old credential and requires fresh ones (FR-006). Snapshot isolation (SC-003) is `009`'s guarantee — editing a name does not change a historical Job's snapshot.

---

## US3: Archive / Restore

```bash
pytest tests/unit/connector_registry/test_service.py -k "archive or restore" -v
```

Archived registrations vanish from the wizard dropdown (via `007`'s `get_active`) and the default list, remain under the `Archived`/`All` filter, and are restorable (FR-014/016).

---

## US5: Hard-delete (gated)

```bash
pytest tests/unit/connector_registry/test_service.py -k "hard_delete" -v
```

- A registration with **zero** Job references hard-deletes (SC-007).
- A registration referenced by any historical Job is **blocked** with `RegistrationInUseError` naming the count; the tester is directed to Archive (SC-006).

---

## Test connection

```bash
pytest tests/unit/connector_registry/test_test_connection.py -v
# Manual: on the create/edit form, click "Test connection" against the running mock —
#   expect "valid contract"; point at a dead port → "unreachable"; never blocks Save.
```

Categories: `valid` / `invalid_contract` / `http_error` / `unreachable` / `timeout` / `tls_failure` / `auth_decrypt_failed` (FR-022/023). Never persists (SC-008).

---

## Pass criteria

```bash
pytest tests/unit/connector_registry tests/integration/test_connector_registry_ui.py -v
ruff check src tests
```

All five user stories verified; credentials never rendered/persisted in plaintext (SC-002); hard-delete gated by Job references; test-connection informational-only.
