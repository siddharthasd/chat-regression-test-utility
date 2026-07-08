"""Unit tests for harness.ui.detail.analytics (feature 018)."""

from __future__ import annotations

import statistics

import pytest

from harness.ui.detail.analytics import ScoreEntry, compute_analytics


def _entry(
    param="relevance", score=0.8, verdict=None, overall_verdict="pass",
    error=False, unit_id=None
):
    return ScoreEntry(
        parameter_name=param,
        score=score,
        reasoning="ok",
        verdict=verdict,
        overall_verdict=overall_verdict,
        error=error,
        unit_id=unit_id,
    )


# ── 1. All error entries → no valid stats; declared dims appear as no_data ────

def test_all_error_entries_empty_result():
    entries = [
        _entry(error=True, unit_id="u1"),
        _entry(error=True, unit_id="u2"),
    ]
    result = compute_analytics(entries, ["relevance"])
    assert result.evaluated_count == 0
    assert result.overall_mean_score is None
    assert result.overall_verdict_distribution == ()
    assert result.error_count == 2
    # Declared dim has no valid entries → appears as a no_data placeholder
    assert len(result.parameters) == 1
    assert result.parameters[0].parameter_name == "relevance"
    assert result.parameters[0].no_data is True


# ── 2. Single valid entry → basic stats correct ──────────────────────────────

def test_single_entry_basic_stats():
    entries = [_entry(score=0.7, unit_id="u1")]
    result = compute_analytics(entries, ["relevance"])
    assert result.evaluated_count == 1
    assert result.overall_mean_score == pytest.approx(0.7)
    assert len(result.parameters) == 1
    p = result.parameters[0]
    assert p.mean == pytest.approx(0.7)
    assert p.median == pytest.approx(0.7)
    assert p.min == pytest.approx(0.7)
    assert p.max == pytest.approx(0.7)
    assert p.range == pytest.approx(0.0)
    assert p.stddev == pytest.approx(0.0)


# ── 3. Multiple entries → correct mean, median, stddev ──────────────────────

def test_multiple_entries_stats():
    scores = [0.2, 0.5, 0.8, 1.0, 0.6]
    entries = [_entry(score=s, unit_id=f"u{i}") for i, s in enumerate(scores)]
    result = compute_analytics(entries, ["relevance"])
    p = result.parameters[0]
    assert p.mean == pytest.approx(statistics.mean(scores))
    assert p.median == pytest.approx(statistics.median(scores))
    assert p.min == pytest.approx(min(scores))
    assert p.max == pytest.approx(max(scores))
    assert p.range == pytest.approx(max(scores) - min(scores))
    assert p.stddev == pytest.approx(statistics.pstdev(scores))


# ── 4. Histogram always has exactly 10 buckets ───────────────────────────────

def test_histogram_always_10_buckets():
    entries = [_entry(score=s, unit_id=f"u{i}") for i, s in enumerate([0.1, 0.5, 0.9])]
    result = compute_analytics(entries, ["relevance"])
    assert len(result.parameters[0].histogram_buckets) == 10


# ── 5. All identical scores → all in bucket 5 (normalised 0.5 → int(5.0)=5) ─

def test_all_identical_scores_single_bucket():
    entries = [_entry(score=0.6, unit_id=f"u{i}") for i in range(5)]
    result = compute_analytics(entries, ["relevance"])
    buckets = result.parameters[0].histogram_buckets
    totals = [b.count for b in buckets]
    # normalised value is 0.5 for all; int(0.5*10)=5 → bucket index 5
    assert totals[5] == 5
    assert sum(totals) == 5
    assert all(b.count == 0 for i, b in enumerate(buckets) if i != 5)


# ── 6. unit_id dedup: overall verdict counts one per unit ────────────────────

def test_unit_id_dedup_overall_verdict():
    # 2 score entries share unit_id "u1" (2 params for 1 utterance)
    entries = [
        ScoreEntry("relevance", 0.8, "", None, "pass", False, "u1"),
        ScoreEntry("tone", 0.9, "", None, "pass", False, "u1"),
        ScoreEntry("relevance", 0.3, "", None, "fail", False, "u2"),
        ScoreEntry("tone", 0.4, "", None, "fail", False, "u2"),
    ]
    result = compute_analytics(entries, ["relevance", "tone"])
    vd = {vc.verdict: vc.count for vc in result.overall_verdict_distribution}
    # u1 → pass (once), u2 → fail (once) — dedup prevents double counting
    assert vd.get("pass", 0) == 1
    assert vd.get("fail", 0) == 1
    assert result.evaluated_count == 2


# ── 7. unit_id dedup: evaluated_count = distinct unit_ids ───────────────────

def test_unit_id_dedup_evaluated_count():
    # 3 entries for 2 distinct units
    entries = [
        ScoreEntry("relevance", 0.7, "", None, "pass", False, "u1"),
        ScoreEntry("tone", 0.8, "", None, "pass", False, "u1"),
        ScoreEntry("relevance", 0.5, "", None, "warn", False, "u2"),
    ]
    result = compute_analytics(entries, ["relevance", "tone"])
    assert result.evaluated_count == 2


# ── 8. Error entries excluded from parameter stats ───────────────────────────

def test_error_entries_excluded_from_stats():
    entries = [
        _entry(score=0.9, unit_id="u1"),
        _entry(score=0.0, error=True, unit_id="u2"),
    ]
    result = compute_analytics(entries, ["relevance"])
    assert result.error_count == 1
    p = result.parameters[0]
    # Only the valid entry contributes to stats
    assert p.mean == pytest.approx(0.9)
    assert p.min == pytest.approx(0.9)


# ── 9. Declared dims appear first in parameters order ────────────────────────

def test_declared_dims_order_first():
    entries = [
        ScoreEntry("tone", 0.8, "", None, "pass", False, "u1"),
        ScoreEntry("relevance", 0.7, "", None, "pass", False, "u1"),
        ScoreEntry("fluency", 0.6, "", None, "pass", False, "u1"),
    ]
    result = compute_analytics(entries, ["relevance", "tone"])
    names = [p.parameter_name for p in result.parameters]
    assert names.index("relevance") < names.index("fluency")
    assert names.index("tone") < names.index("fluency")


# ── 10. Undeclared parameter flagged as unexpected ───────────────────────────

def test_unexpected_param_flagged():
    entries = [
        ScoreEntry("relevance", 0.8, "", None, "pass", False, "u1"),
        ScoreEntry("surprise_dim", 0.5, "", None, "pass", False, "u1"),
    ]
    result = compute_analytics(entries, ["relevance"])
    by_name = {p.parameter_name: p for p in result.parameters}
    assert not by_name["relevance"].is_unexpected
    assert by_name["surprise_dim"].is_unexpected


# ── 11. v1 entries (no verdict) → verdict_distribution is None ───────────────

def test_v1_no_verdict_gives_none_distribution():
    # v1 evaluator: verdict=None on all entries
    entries = [
        ScoreEntry("relevance", 0.8, "", None, "pass", False, "u1"),
        ScoreEntry("relevance", 0.7, "", None, "pass", False, "u2"),
    ]
    result = compute_analytics(entries, ["relevance"])
    p = result.parameters[0]
    assert p.verdict_distribution is None
    assert p.verdict_coverage is None


# ── Bonus: sigma band values clamped to [0, 1] ──────────────────────────────

def test_sigma_band_clamped():
    # stddev larger than range would produce out-of-range sigma values without clamping
    entries = [_entry(score=s, unit_id=f"u{i}") for i, s in enumerate([0.0, 1.0])]
    result = compute_analytics(entries, ["relevance"])
    for b in result.parameters[0].histogram_buckets:
        assert 0.0 <= b.sigma_low <= 1.0
        assert 0.0 <= b.sigma_high <= 1.0
        assert b.sigma_low <= b.sigma_high
