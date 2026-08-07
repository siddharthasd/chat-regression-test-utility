# Tasks: BL-001 — KB Source Traceability

**Plan**: `specs/021-bl001-kb-source-traceability/plan.md`  
**Generated**: 2026-08-07

---

## Phase 1 — Dependency

- [X] T1: Add `openpyxl>=3.1,<4` to `pyproject.toml` `[project.dependencies]`

## Phase 2 — Core logic (`view.py`)

- [X] T2: Add `_extract_sources()` helper + extend `row_view()` with `source_count` and `sources` keys (`src/harness/ui/detail/view.py`)
- [X] T3: Extend `results_csv_builder()` — append `sourceCount` and `retrievedSources` columns (`src/harness/ui/detail/view.py`)
- [X] T4: Extend `results_json_builder()` — append `sources` array to each utterance object (`src/harness/ui/detail/view.py`)
- [X] T5: Add `results_xlsx_builder()` + `_bold_row()` + `_write_data_dictionary()` helpers (`src/harness/ui/detail/view.py`)

## Phase 3 — Route

- [X] T6: Add `GET /jobs/{job_id}/download-results.xlsx` route (`src/harness/ui/detail/routes.py`)

## Phase 4 — Template

- [X] T7: Update `detail/index.html` — rename download buttons, add XLSX button, add Retrieved Context section (`src/harness/ui/detail/templates/detail/index.html`)

## Phase 5 — Tests

- [X] T8: Add unit tests for `_extract_sources`, `row_view` source keys, CSV/JSON/XLSX builders (`tests/unit/detail/test_view.py`)
- [X] T9: Add integration tests for XLSX route (`tests/integration/test_detail_ui.py`)
