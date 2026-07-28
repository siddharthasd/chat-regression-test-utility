"""Parser unit tests (no DB): decode/BOM, RFC-4180, header + row validation (US1/US2/US5)."""

from __future__ import annotations

import codecs

from harness.csv_upload.parser import decode_csv, parse_and_validate
from harness.csv_upload.result import ErrorCategory


def _categories(parsed):
    return {e.category for e in parsed.errors}


# ----------------------------------------------------------------------- US1 decode/parse
def test_valid_parse_preserves_order_and_text() -> None:
    text = "utteranceText,testId\nhello,t1\nworld,t2\n"
    parsed = parse_and_validate(text, require_password=False)
    assert parsed.errors == []
    assert [(r.source_row, r.test_id, r.utterance_text) for r in parsed.rows] == [
        (1, "t1", "hello"),
        (2, "t2", "world"),
    ]


def test_extra_columns_preserved_as_metadata() -> None:
    text = "utteranceText,testId,locale\nhi,t1,en-US\n"
    parsed = parse_and_validate(text, require_password=False)
    assert parsed.rows[0].extra == {"locale": "en-US"}


def test_require_password_toggles_requirement() -> None:
    text = "utteranceText,testId\nhi,t1\n"
    assert parse_and_validate(text, require_password=False).errors == []
    parsed = parse_and_validate(text, require_password=True)
    assert ErrorCategory.MISSING_COLUMN in _categories(parsed)


def test_password_value_captured_when_present() -> None:
    text = "utteranceText,testId,password\nhi,t1,secret\n"
    parsed = parse_and_validate(text, require_password=True)
    assert parsed.rows[0].password == "secret"


def test_column_order_irrelevant_and_header_whitespace_trimmed() -> None:
    text = " password , testId , utteranceText \nsecret,t1,hi\n"
    parsed = parse_and_validate(text, require_password=True)
    assert parsed.errors == []
    assert parsed.rows[0].utterance_text == "hi"
    assert parsed.rows[0].password == "secret"


# --------------------------------------------------------------------------- US2 errors
def test_missing_required_columns_named() -> None:
    parsed = parse_and_validate("utteranceText\nhi\n", require_password=True)
    cats = _categories(parsed)
    assert ErrorCategory.MISSING_COLUMN in cats
    missing = {e.column for e in parsed.errors if e.category == ErrorCategory.MISSING_COLUMN}
    assert missing == {"testId", "password"}


def test_duplicate_column_rejected() -> None:
    parsed = parse_and_validate("utteranceText,testId,testId\nhi,t1,t2\n", require_password=False)
    assert ErrorCategory.DUPLICATE_COLUMN in _categories(parsed)


def test_empty_required_value_per_row() -> None:
    text = "utteranceText,testId\nhi,t1\n  ,t2\nbye,\n"
    parsed = parse_and_validate(text, require_password=False)
    empties = [e for e in parsed.errors if e.category == ErrorCategory.EMPTY_VALUE]
    assert {(e.row, e.column) for e in empties} == {(2, "utteranceText"), (3, "testId")}


def test_row_column_mismatch() -> None:
    text = "utteranceText,testId\nhi,t1,extra\n"
    parsed = parse_and_validate(text, require_password=False)
    assert ErrorCategory.ROW_COLUMN_MISMATCH in _categories(parsed)


def test_no_data_rows() -> None:
    parsed = parse_and_validate("utteranceText,testId\n", require_password=False)
    assert ErrorCategory.NO_DATA_ROWS in _categories(parsed)


def test_unsupported_delimiter() -> None:
    parsed = parse_and_validate("utteranceText;testId\nhi;t1\n", require_password=False)
    assert ErrorCategory.UNSUPPORTED_DELIMITER in _categories(parsed)


def test_invalid_utf8_decode() -> None:
    text, err = decode_csv(b"\xff\xfe bad bytes")
    assert text is None
    assert err.category == ErrorCategory.ENCODING


# --------------------------------------------------------------------------- US5 edges
def test_bom_stripped_silently() -> None:
    raw = codecs.BOM_UTF8 + b"utteranceText,testId\nhi,t1\n"
    text, err = decode_csv(raw)
    assert err is None
    assert text.startswith("utteranceText")  # BOM gone
    parsed = parse_and_validate(text, require_password=False)
    assert parsed.errors == [] and not parsed.warnings


def test_quoted_multiline_value_preserved() -> None:
    text = 'utteranceText,testId\n"line1\nline2",t1\n'
    parsed = parse_and_validate(text, require_password=False)
    assert parsed.rows[0].utterance_text == "line1\nline2"


def test_trailing_blank_rows_skipped_with_warning() -> None:
    text = "utteranceText,testId\nhi,t1\n,\n,\n"
    parsed = parse_and_validate(text, require_password=False)
    assert len(parsed.rows) == 1
    assert any("blank" in w for w in parsed.warnings)
    assert parsed.errors == []


def test_unicode_roundtrip() -> None:
    text = "utteranceText,testId\n🚀 café 日本語,t1\n"
    parsed = parse_and_validate(text, require_password=False)
    assert parsed.rows[0].utterance_text == "🚀 café 日本語"
