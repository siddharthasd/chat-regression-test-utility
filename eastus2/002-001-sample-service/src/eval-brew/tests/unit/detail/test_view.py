"""Unit tests for BL-001 additions to harness.ui.detail.view."""

from __future__ import annotations

import io
import json

import openpyxl
import pytest

from harness.ui.detail.view import (
    _extract_sources,
    results_csv_builder,
    results_flat_csv_builder,
    results_flat_xlsx_builder,
    results_json_builder,
    results_xlsx_builder,
    row_view,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_contract(sources=None, normalized_text="Bot reply"):
    contract = {"chatbotResponse": {"normalizedText": normalized_text}}
    if sources is not None:
        contract["chatbotResponse"]["metadata"] = {"sources": sources}
    return contract


def _make_result(contract=None, verdict="pass", scores=None):
    class FakeResult:
        normalized_contract = contract
        evaluation_verdict = verdict
        evaluation_scores = scores or [{"parameter_name": "relevance", "score": 0.9, "reasoning": "ok"}]
        utterance_intent = "faq"
        error_status = None
        error_stage = None
        error_details = None
        result_metadata = None
        harness_annotations = None
        raw_chatbot_response = None
    return FakeResult()


def _make_utterance(text="Hello?", test_id="t1", contract=None, verdict="pass", sources=None):
    class FakeUtterance:
        utterance_id = "uid-001"
        row_index = 1
        utterance_text = text
        self_test_id = test_id
        extra_metadata = {}
        evaluation_result = _make_result(
            contract=contract or _make_contract(sources=sources),
            verdict=verdict,
        )
    FakeUtterance.test_id = test_id
    return FakeUtterance()


# ── _extract_sources ──────────────────────────────────────────────────────────

def test_extract_sources_returns_all_five_fields():
    contract = _make_contract(sources=[
        {"url": "https://kb/1", "title": "Article 1", "chunk": "some text",
         "scope": "hr", "documentId": "doc-1"},
    ])
    result = _extract_sources(contract)
    assert len(result) == 1
    s = result[0]
    assert s["url"] == "https://kb/1"
    assert s["title"] == "Article 1"
    assert s["chunk"] == "some text"
    assert s["scope"] == "hr"
    assert s["documentId"] == "doc-1"


def test_extract_sources_empty_array():
    assert _extract_sources(_make_contract(sources=[])) == []


def test_extract_sources_missing_metadata_key():
    contract = {"chatbotResponse": {"normalizedText": "hi"}}
    assert _extract_sources(contract) == []


def test_extract_sources_none_contract():
    assert _extract_sources(None) == []


def test_extract_sources_non_list_value_returns_empty():
    contract = _make_contract(sources="not-a-list")
    assert _extract_sources(contract) == []


def test_extract_sources_strips_non_http_url():
    """javascript: and other non-http(s) URLs must be sanitised to '' (XSS prevention)."""
    bad_urls = ["javascript:alert(1)", "data:text/html,hi", "vbscript:x", "ftp://x", "u"]
    for bad_url in bad_urls:
        result = _extract_sources(_make_contract(sources=[
            {"url": bad_url, "title": "T", "chunk": "c", "scope": "s", "documentId": "d"}
        ]))
        assert result[0]["url"] == "", f"expected empty url for {bad_url!r}"

    for good_url in ["https://example.com", "http://localhost/path"]:
        result = _extract_sources(_make_contract(sources=[
            {"url": good_url, "title": "T", "chunk": "c", "scope": "s", "documentId": "d"}
        ]))
        assert result[0]["url"] == good_url


def test_extract_sources_chunk_short_truncated():
    long_chunk = "x" * 201
    contract = _make_contract(sources=[
        {"url": "", "title": "", "chunk": long_chunk, "scope": "", "documentId": ""}
    ])
    result = _extract_sources(contract)
    assert result[0]["chunk"] == long_chunk
    assert result[0]["chunk_short"].endswith("…")
    assert len(result[0]["chunk_short"]) == 201  # 200 chars + ellipsis


def test_extract_sources_chunk_exact_200_not_truncated():
    chunk = "y" * 200
    contract = _make_contract(sources=[
        {"url": "", "title": "", "chunk": chunk, "scope": "", "documentId": ""}
    ])
    result = _extract_sources(contract)
    assert result[0]["chunk_short"] == chunk
    assert "…" not in result[0]["chunk_short"]


def test_extract_sources_skips_non_dict_entries():
    contract = _make_contract(sources=[
        "not-a-dict",
        {"url": "u", "title": "t", "chunk": "c", "scope": "s", "documentId": "d"},
    ])
    result = _extract_sources(contract)
    assert len(result) == 1


# ── row_view source keys ──────────────────────────────────────────────────────

def test_row_view_includes_source_count_and_sources():
    sources = [{"url": "u", "title": "t", "chunk": "c", "scope": "s", "documentId": "d"}]
    u = _make_utterance(sources=sources)
    rv = row_view(u, ["relevance"])
    assert rv["source_count"] == 1
    assert len(rv["sources"]) == 1
    assert rv["sources"][0]["title"] == "t"


def test_row_view_zero_sources_when_no_metadata():
    u = _make_utterance(contract=_make_contract(sources=None))
    rv = row_view(u, ["relevance"])
    assert rv["source_count"] == 0
    assert rv["sources"] == []


# ── results_csv_builder ───────────────────────────────────────────────────────

class _FakeJob:
    job_id = "job-abc12345"
    source_csv_filename = "test.csv"


def _make_utterances_for_csv(sources=None):
    class FakeResult:
        normalized_contract = _make_contract(sources=sources, normalized_text="Answer")
        evaluation_verdict = "pass"
        evaluation_scores = [{"parameter_name": "relevance", "score": 0.9, "reasoning": "ok"}]
        utterance_intent = "faq"
        error_status = None
        error_stage = None

    class FakeUtterance:
        utterance_id = "uid-1"
        row_index = 1
        utterance_text = "Question?"
        test_id = "t1"
        extra_metadata = {}
        evaluation_result = FakeResult()

    return [FakeUtterance()]


def test_csv_header_includes_source_columns():
    _, body = results_csv_builder(_FakeJob(), _make_utterances_for_csv())
    header = body.splitlines()[0]
    for col in ("Source #", "Source Title", "Source URL", "Document ID", "Scope", "Retrieved Text"):
        assert col in header
    assert "sourceCount" not in header
    assert "retrievedSources" not in header
    assert "sourceIndex" not in header


def test_csv_source_count_and_json_in_data_row():
    sources = [{"url": "https://kb.example.com/u", "title": "t", "chunk": "c", "scope": "s", "documentId": "d"}]
    _, body = results_csv_builder(_FakeJob(), _make_utterances_for_csv(sources=sources))
    import csv as csv_mod
    rows = list(csv_mod.DictReader(body.splitlines()))
    assert rows[0]["Source #"] == "1"
    assert rows[0]["Source Title"] == "t"
    assert rows[0]["Source URL"] == "https://kb.example.com/u"
    assert rows[0]["Document ID"] == "d"
    assert rows[0]["Scope"] == "s"
    assert rows[0]["Retrieved Text"] == "c"


def test_csv_zero_sources():
    _, body = results_csv_builder(_FakeJob(), _make_utterances_for_csv(sources=[]))
    import csv as csv_mod
    rows = list(csv_mod.DictReader(body.splitlines()))
    assert rows[0]["Source #"] == ""
    assert rows[0]["Source Title"] == ""
    assert rows[0]["Retrieved Text"] == ""


# ── results_json_builder ──────────────────────────────────────────────────────

def _make_utterances_for_json(sources=None):
    return _make_utterances_for_csv(sources=sources)


def test_json_sources_key_present():
    sources = [{"url": "u", "title": "t", "chunk": "c", "scope": "s", "documentId": "d"}]
    _, body = results_json_builder(_FakeJob(), _make_utterances_for_json(sources=sources))
    data = json.loads(body)
    assert "sources" in data[0]
    assert len(data[0]["sources"]) == 1
    assert data[0]["sources"][0]["chunk"] == "c"


def test_json_sources_empty_when_none():
    _, body = results_json_builder(_FakeJob(), _make_utterances_for_json(sources=None))
    data = json.loads(body)
    assert data[0]["sources"] == []


def test_json_sources_non_ascii_preserved():
    sources = [{"url": "u", "title": "Artículo", "chunk": "tëxt", "scope": "s", "documentId": "d"}]
    _, body = results_json_builder(_FakeJob(), _make_utterances_for_json(sources=sources))
    assert "Artículo" in body
    assert "tëxt" in body


# ── results_xlsx_builder ──────────────────────────────────────────────────────

def _make_utterances_for_xlsx(sources=None):
    return _make_utterances_for_csv(sources=sources)


def test_xlsx_returns_bytes_with_valid_workbook():
    filename, body = results_xlsx_builder(_FakeJob(), _make_utterances_for_xlsx())
    assert filename.endswith("-results.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(body))
    assert wb is not None


def test_xlsx_sheet_names():
    _, body = results_xlsx_builder(_FakeJob(), _make_utterances_for_xlsx())
    wb = openpyxl.load_workbook(io.BytesIO(body))
    assert wb.sheetnames == ["Results", "Retrieved Sources", "Data Dictionary"]


def test_xlsx_sheet1_header():
    _, body = results_xlsx_builder(_FakeJob(), _make_utterances_for_xlsx())
    wb = openpyxl.load_workbook(io.BytesIO(body))
    ws1 = wb["Results"]
    headers = [c.value for c in next(ws1.iter_rows(min_row=1, max_row=1))]
    for col in ("Source #", "Source Title", "Source URL", "Document ID", "Scope", "Retrieved Text"):
        assert col in headers
    assert "sourceCount" not in headers
    assert "retrievedSources" not in headers
    assert "utteranceText" not in headers
    assert "User Question" in headers


def test_xlsx_sheet1_row_count_matches_scores():
    _, body = results_xlsx_builder(_FakeJob(), _make_utterances_for_xlsx())
    wb = openpyxl.load_workbook(io.BytesIO(body))
    # header + 1 score row = 2 rows
    assert wb["Results"].max_row == 2


def test_xlsx_sheet2_populated_with_sources():
    sources = [
        {"url": "u1", "title": "T1", "chunk": "c1", "scope": "s", "documentId": "d1"},
        {"url": "u2", "title": "T2", "chunk": "c2", "scope": "s", "documentId": "d2"},
    ]
    _, body = results_xlsx_builder(_FakeJob(), _make_utterances_for_xlsx(sources=sources))
    wb = openpyxl.load_workbook(io.BytesIO(body))
    ws2 = wb["Retrieved Sources"]
    # header + 2 source rows
    assert ws2.max_row == 3
    rows = list(ws2.iter_rows(min_row=2, values_only=True))
    assert rows[0][3] == 1  # sourceIndex 1-based
    assert rows[1][3] == 2


def test_xlsx_sheet2_empty_for_zero_sources():
    _, body = results_xlsx_builder(_FakeJob(), _make_utterances_for_xlsx(sources=[]))
    wb = openpyxl.load_workbook(io.BytesIO(body))
    # header only
    assert wb["Retrieved Sources"].max_row == 1


def test_xlsx_sheet3_data_dictionary_present():
    _, body = results_xlsx_builder(_FakeJob(), _make_utterances_for_xlsx())
    wb = openpyxl.load_workbook(io.BytesIO(body))
    ws3 = wb["Data Dictionary"]
    first_cell = ws3.cell(1, 1).value
    assert first_cell == "Sheet 1 — Results: Column Definitions"


def test_xlsx_filename_uses_csv_basename():
    job = _FakeJob()
    job.source_csv_filename = "my_run.csv"
    filename, _ = results_xlsx_builder(job, _make_utterances_for_xlsx())
    assert filename == "my_run-results.xlsx"


# ── results_flat_csv_builder ──────────────────────────────────────────────────

def _make_utterances_flat(sources=None):
    return _make_utterances_for_csv(sources=sources)


def _make_utterances_flat_multi():
    """Two utterances with different scores to test dynamic dim columns."""
    sources_a = [{"url": "u1", "title": "T1", "chunk": "c1", "scope": "s", "documentId": "d1"}]
    sources_b = [
        {"url": "u2", "title": "T2", "chunk": "c2", "scope": "s", "documentId": "d2"},
        {"url": "u3", "title": "T3", "chunk": "c3", "scope": "s", "documentId": "d3"},
    ]

    def _make_u(text, tid, contract, scores):
        class FakeResult:
            normalized_contract = contract
            evaluation_verdict = "pass"
            evaluation_scores = scores
            utterance_intent = "faq"
            error_status = None
            error_stage = None

        class FakeUtterance:
            utterance_id = f"uid-{tid}"
            row_index = 1
            utterance_text = text
            test_id = tid
            extra_metadata = {}
            evaluation_result = FakeResult()

        return FakeUtterance()

    u1 = _make_u(
        "Q1", "t1",
        _make_contract(sources=sources_a, normalized_text="A1"),
        [{"parameter_name": "relevance", "score": 0.9, "verdict": "pass", "reasoning": "good"},
         {"parameter_name": "tone", "score": 0.8, "verdict": "pass", "reasoning": "ok"}],
    )
    u2 = _make_u(
        "Q2", "t2",
        _make_contract(sources=sources_b, normalized_text="A2"),
        [{"parameter_name": "relevance", "score": 0.5, "verdict": "fail", "reasoning": "poor"},
         {"parameter_name": "tone", "score": 0.7, "verdict": "warn", "reasoning": "meh"}],
    )
    return [u1, u2]


def test_flat_csv_one_row_per_utterance():
    utterances = _make_utterances_flat_multi()
    _, body = results_flat_csv_builder(_FakeJob(), utterances)
    lines = [l for l in body.splitlines() if l]
    assert len(lines) == 3  # header + 2 utterances


def test_flat_csv_fixed_columns_present():
    _, body = results_flat_csv_builder(_FakeJob(), _make_utterances_flat())
    header = body.splitlines()[0]
    for col in ("User Question", "Test Case Reference", "Intent Category",
                "Chatbot Answer", "Overall Result"):
        assert col in header


def test_flat_csv_dimension_columns_named_correctly():
    utterances = _make_utterances_flat_multi()
    _, body = results_flat_csv_builder(_FakeJob(), utterances)
    header = body.splitlines()[0]
    for col in ("relevance: Score (0–1)", "relevance: Result", "relevance: Justification",
                "tone: Score (0–1)", "tone: Result", "tone: Justification"):
        assert col in header


def test_flat_csv_source_columns_named_correctly():
    utterances = _make_utterances_flat_multi()  # max 2 sources
    _, body = results_flat_csv_builder(_FakeJob(), utterances)
    header = body.splitlines()[0]
    for col in ("Source 1: Title", "Source 1: URL", "Source 1: Document ID",
                "Source 1: Scope", "Source 1: Retrieved Text",
                "Source 2: Title", "Source 2: URL"):
        assert col in header


def test_flat_csv_no_source_columns_when_no_sources():
    _, body = results_flat_csv_builder(_FakeJob(), _make_utterances_flat(sources=[]))
    header = body.splitlines()[0]
    assert "Source 1" not in header


def test_flat_csv_dim_values_correct():
    utterances = _make_utterances_flat_multi()
    _, body = results_flat_csv_builder(_FakeJob(), utterances)
    import csv as csv_mod
    rows = list(csv_mod.DictReader(body.splitlines()))
    assert rows[0]["relevance: Score (0–1)"] == "0.9"
    assert rows[0]["tone: Result"] == "pass"
    assert rows[1]["relevance: Score (0–1)"] == "0.5"
    assert rows[1]["tone: Result"] == "warn"


def test_flat_csv_sparse_source_cols_empty():
    utterances = _make_utterances_flat_multi()  # u1 has 1 src, u2 has 2 srcs
    _, body = results_flat_csv_builder(_FakeJob(), utterances)
    import csv as csv_mod
    rows = list(csv_mod.DictReader(body.splitlines()))
    # u1 has only 1 source — Source 2 columns should be blank
    assert rows[0]["Source 2: Title"] == ""
    assert rows[0]["Source 2: Retrieved Text"] == ""
    # u2 has 2 sources — both populated
    assert rows[1]["Source 1: Title"] == "T2"
    assert rows[1]["Source 2: Title"] == "T3"


# ── results_flat_xlsx_builder ─────────────────────────────────────────────────

def test_flat_xlsx_sheet_names():
    _, body = results_flat_xlsx_builder(_FakeJob(), _make_utterances_flat())
    wb = openpyxl.load_workbook(io.BytesIO(body))
    assert wb.sheetnames == ["Results (Flat)", "Data Dictionary"]


def test_flat_xlsx_header_matches_flat_csv():
    utterances = _make_utterances_flat_multi()
    _, csv_body = results_flat_csv_builder(_FakeJob(), utterances)
    _, xlsx_body = results_flat_xlsx_builder(_FakeJob(), utterances)
    csv_header = csv_body.splitlines()[0].split(",")
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_body))
    xlsx_header = [c.value for c in next(wb["Results (Flat)"].iter_rows(min_row=1, max_row=1))]
    assert csv_header == xlsx_header


def test_flat_xlsx_one_row_per_utterance():
    utterances = _make_utterances_flat_multi()
    _, body = results_flat_xlsx_builder(_FakeJob(), utterances)
    wb = openpyxl.load_workbook(io.BytesIO(body))
    # header + 2 utterance rows
    assert wb["Results (Flat)"].max_row == 3


def test_flat_xlsx_data_dictionary_present():
    _, body = results_flat_xlsx_builder(_FakeJob(), _make_utterances_flat())
    wb = openpyxl.load_workbook(io.BytesIO(body))
    ws2 = wb["Data Dictionary"]
    first_cell = ws2.cell(1, 1).value
    assert first_cell == "Fixed Columns"


def test_flat_csv_friendly_names_not_engineering():
    """Engineering column names must not leak into stakeholder headers."""
    utterances = _make_utterances_flat_multi()
    _, body = results_flat_csv_builder(_FakeJob(), utterances)
    header = body.splitlines()[0]
    for bad in ("utteranceText", "testId", "overallVerdict", "utteranceIntent",
                "chatbotResponse", "source1_title", "relevance_score"):
        assert bad not in header, f"Engineering label leaked: {bad}"


def test_csv_friendly_names_not_engineering():
    """Engineering column names must not leak into long-format stakeholder headers."""
    _, body = results_csv_builder(_FakeJob(), _make_utterances_for_csv())
    header = body.splitlines()[0]
    for bad in ("utteranceText", "testId", "overallVerdict", "parameterName",
                "sourceIndex", "chatbotResponse"):
        assert bad not in header, f"Engineering label leaked: {bad}"
