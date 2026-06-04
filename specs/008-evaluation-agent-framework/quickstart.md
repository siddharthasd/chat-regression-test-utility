# Quickstart: Evaluation Agent Framework (Module 7)

**Date**: 2026-06-04
**Plan**: `specs/008-evaluation-agent-framework/plan.md`

End-to-end verification, organized by user story. Built on `foundation` (010+009+006), sibling to `007`.

---

## Prerequisites

- `pip install -e .[dev]` (adds `httpx`).
- `foundation` code present (evaluator registry + encryption from `009`).

---

## US1 + US5: Evaluate a contract via the bundled mock evaluator

### Automated (canonical)

```bash
pytest tests/integration/test_evaluator_e2e.py -v
pytest tests/integration/test_mock_evaluator.py -v
```

### Manual

```bash
# 1. Launch the mock evaluator (declaring two dimensions, auth none):
harness mock-evaluator --port 9020 --dimensions relevance,groundedness
# 2. Dispatch a contract instance at it:
python - <<'EOF'
from harness.evaluator import dispatch_evaluation, EvaluatorSnapshot
contract = {
  "contractVersion":"1","utteranceId":"u-1","utteranceText":"hi","testId":"t1",
  "conversationContext":None,"connectorId":"c","timestamp":"2026-06-04T12:00:00Z",
  "chatbotResponse":{"rawPayload":{},"normalizedText":"hello","agentChain":[],"metadata":{}},
}
snap = EvaluatorSnapshot("mock-evaluator","http://127.0.0.1:9020",{"mode":"none"},10,
                         ["relevance","groundedness"])
r = dispatch_evaluation(snap, contract)
print("ok:", r.ok, "| verdict:", (r.evaluation_result or {}).get("evaluationVerdict"),
      "| dims:", [s["parameter_name"] for s in (r.evaluation_result or {}).get("evaluationScores",[])],
      "| annotations:", r.harness_annotations)
EOF
# Expected: ok: True | verdict: pass|fail|warn | dims: ['relevance','groundedness'] | annotations: {'unexpected_score_dimensions': []}
```

---

## US2: Add an evaluator with zero core changes

```bash
pytest tests/integration/test_evaluator_e2e.py::test_register_and_run_no_core_change -v
```

Registers the mock via `009`'s repo, discovers it via `EvaluatorRegistryReader.list_active()`, runs — no source change.

---

## US3: Declared dimensions + unexpected-dimension annotation

```bash
pytest tests/unit/evaluator/test_validation.py -k "annotation or dimension" -v
pytest tests/unit/evaluator/test_registry_read.py::test_get_declared_dimensions -v
# Manual: run the mock with an out-of-declared name and see the soft warning:
harness mock-evaluator --port 9020 --mode unexpected_dims --dimensions relevance
```

`harnessAnnotations.unexpected_score_dimensions` lists any emitted `parameter_name` not in the declared list; the row is **not** rejected (FR-005a).

---

## US4: Non-determinism (no caching)

```bash
pytest tests/integration/test_evaluator_e2e.py -k "same_input or one_request" -v
```

Dispatching the same contract twice issues two POSTs (SC-006); the two results differ in verdict/scores/reasoning (SC-005).

---

## Error-stage mapping via mock modes

```bash
harness mock-evaluator --port 9020 --mode status500     # non-2xx → evaluator_response
harness mock-evaluator --port 9020 --mode nonconformant # 2xx bad result → evaluator_result
harness mock-evaluator --port 9020 --mode slow          # sleep past timeout → evaluator_transport
```

---

## Pass criteria

```bash
pytest tests/unit/evaluator tests/integration/test_evaluator_e2e.py tests/integration/test_mock_evaluator.py -v
ruff check src tests
```

All five user stories verified; one request per row, never cached; malformed results → `evaluator_result`; declared-dimension drift annotated (not rejected); credentials never in plaintext; mock runs with zero external setup and non-deterministic output.
