# Quickstart: Standard Evaluation Contract (Module 6)

**Date**: 2026-06-03
**Plan**: `specs/006-evaluation-contract/plan.md`

End-to-end verification of the `006` implementation, organized by user story. The automated test is the canonical pass signal; a manual CLI path supports authoring-time verification (FR-010).

---

## Prerequisites

- `pip install -e .[dev]` (adds `jsonschema` after `pyproject.toml` is updated).
- The `010` foundation (`src/harness/` package skeleton) is present (grafted, as for `009`).

---

## US1: A conforming instance passes and is forwardable

### Automated (canonical)

```bash
pytest tests/unit/contract/test_validation.py::test_conformant_instance_passes -v
```

### Manual (CLI authoring path, FR-010)

```bash
# Write a minimal conforming instance:
python - <<'EOF'
import json
json.dump({
  "contractVersion": "1",
  "utteranceId": "11111111-1111-4111-8111-111111111111",
  "utteranceText": "What is my balance?",
  "testId": "row-1",
  "conversationContext": None,
  "connectorId": "conn-abc",
  "timestamp": "2026-06-03T12:00:00Z",
  "chatbotResponse": {
    "rawPayload": {"text": "Your balance is $100."},
    "normalizedText": "Your balance is $100.",
    "agentChain": [],
    "metadata": {}
  }
}, open("good.json","w"))
EOF

harness contract validate good.json
# Expected: VALID   (exit code 0)
```

---

## US2: A non-conforming instance is rejected with detail

### Automated (canonical)

```bash
pytest tests/unit/contract/test_validation.py -k "missing or type or format or password or version" -v
```

### Manual

```bash
# Missing utteranceId + non-ISO timestamp:
python - <<'EOF'
import json
json.dump({
  "contractVersion": "1", "utteranceText": "hi", "testId": "r1",
  "conversationContext": None, "connectorId": "c", "timestamp": 1717416000,
  "chatbotResponse": {"rawPayload": {}, "normalizedText": "x", "agentChain": [], "metadata": {}}
}, open("bad.json","w"))
EOF

harness contract validate bad.json --json
# Expected: INVALID (exit code 1); violations name `utteranceId` (missing) and `timestamp` (wrong_type)
```

---

## US3: Unknown extension field validates as conforming

### Automated (canonical)

```bash
pytest tests/unit/contract/test_validation.py::test_unknown_fields_ok -v
```

Confirms an instance with `chatbotResponse.metadata.toolCallCount` (and any other unknown field) validates, and `contractVersion` is unchanged (FR-005/FR-006).

---

## US4: Versioning policy + runtime version gate

### Automated (canonical)

```bash
pytest tests/unit/contract/test_versioning.py -v
```

Covers: numeric (not lexicographic) comparison (`"10"` > `"2"`); `contractVersion` greater than bundled is rejected with both versions named (SC-004); additive change does not bump (SC-006); breaking-change policy test (SC-007); determinism (SC-009).

### Manual: contractVersion ahead of the harness

```bash
python - <<'EOF'
import json
d = json.load(open("good.json")); d["contractVersion"] = "2"
json.dump(d, open("future.json","w"))
EOF

harness contract validate future.json
# Expected: INVALID (exit 1); message names instance version "2", bundled version "1",
#           suggests updating the harness; kind = version_out_of_range
```

---

## Pass criteria

```bash
pytest tests/unit/contract tests/integration/test_contract_cli.py -v
ruff check src tests
```

All four user stories verified; validation is reachable both as `harness.contract.validate_contract()` and via `harness contract validate`; the version gate rejects ahead-of-harness instances; no `password` key validates at any depth.
