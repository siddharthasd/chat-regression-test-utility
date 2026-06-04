# Quickstart: Evaluator Registry & Management (Module 14)

**Date**: 2026-06-04
**Plan**: `specs/014-evaluator-registry-management/plan.md`

End-to-end verification, organized by user story. Built on `foundation` (incl. 013). Mirrors `013`'s quickstart. Automated tests use Flask's test client; the manual path uses the running UI + the bundled mock evaluator (008).

---

## Prerequisites

- `pip install -e .[dev]` (no new deps).
- Manual path: `harness mock-evaluator --port 9020 --dimensions relevance,groundedness`.

---

## US1 + US5: Register and list evaluators

```bash
pytest tests/integration/test_evaluator_registry_ui.py -v
pytest tests/unit/evaluator_registry -v
```

Manual: `harness serve` → `http://127.0.0.1:5000/evaluators` → "Register new evaluator"; fill name/description/endpoint, auth none, timeout 60, dimensions (one per line). Save; verify it lists; toggle Active/Archived/All; search; note the dimension preview (first 3 + "+ N more").

---

## US2 + US3: Edit + declared scoring dimensions

```bash
pytest tests/unit/evaluator_registry/test_service.py -k "update or dimension or mode_change" -v
pytest tests/unit/evaluator_registry/test_forms.py -k "dimension" -v
```

Covers: credential replace/preserve, mode-change discard; dimensions trimmed, blanks dropped, **order preserved** (SC-011), duplicates warned (FR-009), empty list valid (SC-012). Snapshot isolation (SC-003/004) is `009`'s guarantee.

---

## US4: Archive / Restore

```bash
pytest tests/unit/evaluator_registry/test_service.py -k "archive or restore" -v
```

Archived evaluators leave the wizard dropdown (`008`'s `get_active`) and the default list; restorable.

---

## US6: Hard-delete (gated)

```bash
pytest tests/unit/evaluator_registry/test_service.py -k "hard_delete" -v
```

Blocked with `RegistrationInUseError` when a historical Job references the evaluator (SC-007); succeeds when unreferenced (SC-008).

---

## Test connection

```bash
pytest tests/unit/evaluator_registry/test_test_connection.py -v
# Manual: with the mock evaluator running, "Test connection" → "valid EvaluationResult";
#   point at a dead port → "unreachable"; declare dimensions the mock won't emit → soft warning. Never blocks Save.
```

Validates the response as an **EvaluationResult** (`008 FR-005b`); soft-warns on dimension divergence (FR-029). Categories: `valid`/`invalid_result`/`http_error`/`unreachable`/`timeout`/`auth_decrypt_failed`.

---

## Pass criteria

```bash
pytest tests/unit/evaluator_registry tests/integration/test_evaluator_registry_ui.py -v
ruff check src tests
```

All six user stories verified; credentials never plaintext (SC-002); dimensions order-preserved; hard-delete gated; test-connection informational-only and EvaluationResult-aware.
