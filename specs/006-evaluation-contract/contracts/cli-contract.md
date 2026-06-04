# Contract: `harness contract validate` CLI

**Module**: `harness.cli.contract`
**Stability**: Authoring tool (FR-010) — for connector/evaluator developers validating hand-rolled instances outside a running job.

---

## Command

```text
harness contract validate <path-to-json-file> [--json]
```

- Reads the JSON file at `<path>`, decodes it, and runs `harness.contract.validate_contract`.
- **Human output** (default): `VALID` on success; otherwise `INVALID` followed by one line per violation: `  <field_path>: <kind> — <message>`.
- **`--json`**: emits the `ValidationResult` as JSON: `{"valid": bool, "contractVersion": str|null, "violations": [{"fieldPath","kind","message","expected","observed"}]}`.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Instance conforms (`valid == true`). |
| `1` | Instance does not conform (one or more violations). |
| `2` | Usage error — file not found, or file is not valid JSON. |

## Notes

- Registered as a `contract` command group on the existing `harness` Click group (mirrors `cli/info.py`).
- Uses the same `validate_contract` implementation as the runtime path, so CLI and runtime verdicts are always identical (FR-008/FR-011).
- Read-only; performs no persistence and no network access.
