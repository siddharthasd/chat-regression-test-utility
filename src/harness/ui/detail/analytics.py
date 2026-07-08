"""Shared RunAnalytics engine (018). Pure functions — no ORM, no FastAPI, no Jinja2.

Consumed by:
  - harness.ui.detail.routes (batch job analytics — 018)
  - harness.ui.chat_session.routes (live chat analytics — 019)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreEntry:
    parameter_name: str
    score: float
    reasoning: str
    verdict: str | None
    overall_verdict: str | None
    error: bool
    unit_id: str | None = None  # utterance_id or turn_id; enables dedup for overall counts
    utterance_intent: str | None = None  # evaluator-identified intent for this utterance


@dataclass(frozen=True)
class VerdictCount:
    verdict: str
    count: int
    pct: float


@dataclass(frozen=True)
class HistogramBucket:
    index: int
    raw_low: float
    raw_high: float
    count: int
    sigma_low: float
    sigma_high: float


@dataclass(frozen=True)
class ParameterStats:
    parameter_name: str
    parameter_id: str
    mean: float
    median: float
    min: float
    max: float
    range: float
    stddev: float
    histogram_buckets: tuple[HistogramBucket, ...]
    verdict_distribution: tuple[VerdictCount, ...] | None
    verdict_coverage: int | None
    is_unexpected: bool
    no_data: bool = False  # True when declared but every entry was an error


@dataclass(frozen=True)
class IntentStats:
    intent: str
    mean_score: float
    count: int  # distinct utterances carrying this intent
    verdict_distribution: tuple[VerdictCount, ...] | None


_MAX_INTENT_ROWS = 20


@dataclass(frozen=True)
class RunAnalytics:
    overall_mean_score: float | None
    overall_verdict_distribution: tuple[VerdictCount, ...]
    parameters: tuple[ParameterStats, ...]
    evaluated_count: int
    error_count: int
    intent_breakdown: tuple[IntentStats, ...] = ()
    intent_total_count: int = 0  # distinct intents seen before cap


def _derive_parameter_id(name: str) -> str:
    return name.lower().replace(" ", "_")


def _normalise(scores: list[float]) -> list[float]:
    mn = min(scores)
    mx = max(scores)
    if mn == mx:
        return [0.5] * len(scores)
    rng = mx - mn
    return [(x - mn) / rng for x in scores]


def _build_histogram(
    normalised: list[float],
    raw_min: float,
    raw_max: float,
    mean: float,
    stddev: float,
) -> tuple[HistogramBucket, ...]:
    counts = [0] * 10
    for n in normalised:
        bucket = min(int(n * 10), 9)
        counts[bucket] += 1

    rng = raw_max - raw_min
    if rng == 0:
        sigma_low = sigma_high = 0.5
    else:
        sigma_low = max(0.0, min(1.0, (mean - stddev - raw_min) / rng))
        sigma_high = max(0.0, min(1.0, (mean + stddev - raw_min) / rng))

    buckets = []
    for i in range(10):
        norm_low = i / 10
        norm_high = (i + 1) / 10
        if rng == 0:
            raw_low = raw_high = raw_min
        else:
            raw_low = raw_min + norm_low * rng
            raw_high = raw_min + norm_high * rng
        buckets.append(
            HistogramBucket(
                index=i,
                raw_low=raw_low,
                raw_high=raw_high,
                count=counts[i],
                sigma_low=sigma_low,
                sigma_high=sigma_high,
            )
        )
    return tuple(buckets)


def _build_verdict_dist(verdicts: list[str]) -> tuple[VerdictCount, ...] | None:
    if not verdicts:
        return None
    total = len(verdicts)
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v] = counts.get(v, 0) + 1
    return tuple(
        VerdictCount(verdict=v, count=c, pct=round(c / total * 100, 1))
        for v, c in sorted(counts.items(), key=lambda x: -x[1])
    )


def _build_intent_breakdown(valid: list[ScoreEntry]) -> tuple[tuple[IntentStats, ...], int]:
    """Return (capped intent stats sorted by mean_score desc, total distinct intent count)."""
    groups: dict[str, list[ScoreEntry]] = {}
    for e in valid:
        if not e.utterance_intent:
            continue
        groups.setdefault(e.utterance_intent, []).append(e)

    stats: list[IntentStats] = []
    for intent, entries in groups.items():
        # count = distinct unit_ids for this intent
        unit_ids = {e.unit_id for e in entries if e.unit_id is not None}
        count = len(unit_ids) + sum(1 for e in entries if e.unit_id is None)

        # mean score: only real parameter entries (exclude parameter_name="" sentinels)
        scores = [e.score for e in entries if e.parameter_name]
        mean_score = statistics.mean(scores) if scores else 0.0

        # verdict distribution: one overall_verdict per deduped unit
        seen: set[str] = set()
        verdicts: list[str] = []
        for e in entries:
            if e.unit_id is None:
                if e.overall_verdict is not None:
                    verdicts.append(e.overall_verdict)
            elif e.unit_id not in seen:
                seen.add(e.unit_id)
                if e.overall_verdict is not None:
                    verdicts.append(e.overall_verdict)

        stats.append(IntentStats(
            intent=intent,
            mean_score=mean_score,
            count=count,
            verdict_distribution=_build_verdict_dist(verdicts),
        ))

    total = len(stats)
    stats.sort(key=lambda s: -s.mean_score)
    return tuple(stats[:_MAX_INTENT_ROWS]), total


def compute_analytics(
    entries: list[ScoreEntry],
    declared_dims: list[str],
) -> RunAnalytics:
    """Aggregate ScoreEntry list into RunAnalytics.

    entries       — all score entries for the job/session (including error rows)
    declared_dims — ordered list of declared parameter names
    """
    valid = [e for e in entries if not e.error]

    # error_count: count distinct errored units (not entries) to avoid N-params inflation.
    error_entries = [e for e in entries if e.error]
    error_unit_ids = {e.unit_id for e in error_entries if e.unit_id is not None}
    error_count = len(error_unit_ids) + sum(1 for e in error_entries if e.unit_id is None)

    # Deduplicate per unit_id for overall verdict counting and evaluated_count.
    # In the has_unit_ids=True branch, entries with unit_id=None are excluded from
    # overall counts (no ID → can't attribute to a distinct unit without inflating).
    has_unit_ids = any(e.unit_id is not None for e in valid)
    if has_unit_ids:
        seen_units: set[str] = set()
        deduped_for_overall: list[ScoreEntry] = []
        for e in valid:
            if e.unit_id is None:
                # Mixed caller: skip None entries — can't dedup, would inflate counts.
                continue
            if e.unit_id not in seen_units:
                deduped_for_overall.append(e)
                seen_units.add(e.unit_id)
        evaluated_count = len(seen_units)
        overall_verdicts = [
            e.overall_verdict for e in deduped_for_overall if e.overall_verdict is not None
        ]
    else:
        evaluated_count = len(valid)
        overall_verdicts = [e.overall_verdict for e in valid if e.overall_verdict is not None]

    overall_mean_score = sum(e.score for e in valid) / len(valid) if valid else None
    overall_verdict_dist = _build_verdict_dist(overall_verdicts) or ()

    # Per-parameter stats: declared order first, then unexpected.
    all_param_names: list[str] = list(declared_dims)
    for e in valid:
        if e.parameter_name and e.parameter_name not in all_param_names:
            all_param_names.append(e.parameter_name)

    param_stats: list[ParameterStats] = []
    seen_param_names: set[str] = set()

    for name in all_param_names:
        if not name:
            continue
        param_entries = [e for e in valid if e.parameter_name == name]
        seen_param_names.add(name)

        if not param_entries:
            # Declared dim with no valid entries — show as no_data placeholder.
            param_stats.append(
                ParameterStats(
                    parameter_name=name,
                    parameter_id=_derive_parameter_id(name),
                    mean=0.0,
                    median=0.0,
                    min=0.0,
                    max=0.0,
                    range=0.0,
                    stddev=0.0,
                    histogram_buckets=(),
                    verdict_distribution=None,
                    verdict_coverage=None,
                    is_unexpected=False,
                    no_data=True,
                )
            )
            continue

        scores = [e.score for e in param_entries]
        mn = min(scores)
        mx = max(scores)
        mean = statistics.mean(scores)
        med = statistics.median(scores)
        rng = mx - mn
        stddev = statistics.pstdev(scores)

        normalised = _normalise(scores)
        histogram = _build_histogram(normalised, mn, mx, mean, stddev)

        param_verdicts = [e.verdict for e in param_entries if e.verdict is not None]
        verdict_dist = _build_verdict_dist(param_verdicts)
        verdict_coverage = len(param_verdicts) if param_verdicts else None

        param_stats.append(
            ParameterStats(
                parameter_name=name,
                parameter_id=_derive_parameter_id(name),
                mean=mean,
                median=med,
                min=mn,
                max=mx,
                range=rng,
                stddev=stddev,
                histogram_buckets=histogram,
                verdict_distribution=verdict_dist,
                verdict_coverage=verdict_coverage,
                is_unexpected=name not in declared_dims,
                no_data=False,
            )
        )

    intent_breakdown, intent_total_count = _build_intent_breakdown(valid)

    return RunAnalytics(
        overall_mean_score=overall_mean_score,
        overall_verdict_distribution=overall_verdict_dist,
        parameters=tuple(param_stats),
        evaluated_count=evaluated_count,
        error_count=error_count,
        intent_breakdown=intent_breakdown,
        intent_total_count=intent_total_count,
    )
