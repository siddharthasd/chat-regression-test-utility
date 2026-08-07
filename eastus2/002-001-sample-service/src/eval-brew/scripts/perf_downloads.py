"""Download builder performance benchmark.

Measures wall-clock time and output size for all four download builders
(CSV, XLSX, Flat CSV, Flat XLSX) at utterance counts 250 / 500 / 750 / 1000.

Profile: 2 dimensions (relevance + tone), 3 KB sources per utterance.
Run from the repo root with the virtualenv active:
    python scripts/perf_downloads.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure src/ is importable when run from repo root or scripts/
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "src"))

from harness.ui.detail.view import (
    results_csv_builder,
    results_flat_csv_builder,
    results_flat_xlsx_builder,
    results_xlsx_builder,
)

# ── Fake data factories ───────────────────────────────────────────────────────

_SOURCES = [
    {
        "url": f"https://kb.example.com/article-{i}",
        "title": f"KB Article {i}: How to configure the system",
        "chunk": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 4,
        "scope": "hr-policy",
        "documentId": f"doc-{i:04d}",
    }
    for i in range(1, 4)
]

_SCORES = [
    {"parameter_name": "relevance", "score": 0.87, "verdict": "pass",
     "reasoning": "The response directly addresses the user question with accurate detail."},
    {"parameter_name": "tone", "score": 0.74, "verdict": "warn",
     "reasoning": "Tone is mostly appropriate but slightly formal for the context."},
]


def _make_contract():
    return {
        "chatbotResponse": {
            "normalizedText": "Thank you for your question. Based on our HR policy documents, "
                              "the answer is as follows: employees are entitled to 20 days of "
                              "annual leave per calendar year, accrued monthly.",
            "metadata": {"sources": _SOURCES},
        }
    }


def _make_utterances(n: int):
    contract = _make_contract()

    class _Result:
        normalized_contract = contract
        evaluation_verdict = "pass"
        evaluation_scores = _SCORES
        utterance_intent = "hr-faq"
        error_status = None
        error_stage = None

    results = []
    for i in range(n):
        class _U:
            utterance_id = f"uid-{i:06d}"
            row_index = i + 1
            utterance_text = f"What is the annual leave policy? (row {i + 1})"
            test_id = f"T{(i % 20) + 1:03d}"
            extra_metadata = {}
            evaluation_result = _Result()

        _U.__name__ = f"U{i}"
        results.append(_U())
    return results


class _FakeJob:
    job_id = "perf-test-job-0001"
    source_csv_filename = "perf_test.csv"


# ── Benchmark runner ──────────────────────────────────────────────────────────

COUNTS = [250, 500, 750, 1000]
RUNS = 3  # average over this many runs per cell

Row = dict  # type alias for readability


def _bench(fn, job, utterances) -> tuple[float, int]:
    """Return (avg_elapsed_seconds, output_bytes)."""
    times = []
    size = 0
    for _ in range(RUNS):
        t0 = time.perf_counter()
        _, out = fn(job, utterances)
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        size = len(out.encode("utf-8") if isinstance(out, str) else out)
    return sum(times) / len(times), size


def run() -> list[Row]:
    job = _FakeJob()
    rows: list[Row] = []
    for n in COUNTS:
        print(f"  n={n:4d} ...", end=" ", flush=True)
        utterances = _make_utterances(n)
        builders = [
            ("CSV (long format)",  results_csv_builder),
            ("XLSX (long format)", results_xlsx_builder),
            ("Flat CSV",           results_flat_csv_builder),
            ("Flat XLSX",          results_flat_xlsx_builder),
        ]
        for label, fn in builders:
            avg, size = _bench(fn, job, utterances)
            rows.append({"n": n, "format": label, "elapsed_s": avg, "size_bytes": size})
            print(".", end="", flush=True)
        print()
    return rows


# ── Markdown output ───────────────────────────────────────────────────────────

def _fmt_ms(s: float) -> str:
    return f"{s * 1000:.0f} ms"


def _fmt_kb(b: int) -> str:
    if b >= 1_048_576:
        return f"{b / 1_048_576:.1f} MB"
    return f"{b / 1024:.0f} KB"


def build_markdown(rows: list[Row]) -> str:
    import datetime, platform, subprocess

    try:
        py_ver = platform.python_version()
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        py_ver = sys.version.split()[0]
        git_sha = "unknown"

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Download Builder Performance",
        "",
        f"**Date:** {now}  ",
        f"**Git SHA:** `{git_sha}`  ",
        f"**Python:** {py_ver}  ",
        f"**Profile:** 2 dimensions (relevance + tone), 3 KB sources per utterance  ",
        f"**Method:** avg of {RUNS} runs per cell, builders called directly (no HTTP overhead)",
        "",
        "## Results",
        "",
        "| Utterances | Format | Avg time | File size |",
        "|:----------:|:-------|:--------:|----------:|",
    ]

    for r in rows:
        lines.append(
            f"| {r['n']:>10,} | {r['format']:<20} | {_fmt_ms(r['elapsed_s']):>8} "
            f"| {_fmt_kb(r['size_bytes']):>9} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- **Long-format** builders produce one row per *(utterance × dimension × source)*.",
        "  At 2 dims × 3 sources, each utterance expands to 6 rows.",
        "- **Flat** builders produce one row per utterance with dynamic columns.",
        "  Column count = 5 fixed + 6 dim cols (2 × 3) + 15 source cols (3 × 5) = 26 columns.",
        "- XLSX builders use `write_only=True` (openpyxl streaming mode), which avoids holding",
        "  cell objects in RAM and keeps memory usage roughly proportional to a single row.",
        "- File sizes grow linearly with utterance count; the XLSX ZIP compression ratio",
        "  improves as repetition increases, so per-row cost decreases at higher counts.",
        "",
    ]

    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Running {RUNS} reps × {len(COUNTS)} counts × 4 formats …")
    rows = run()
    md = build_markdown(rows)

    out_path = _root / "docs" / "tests" / "download-performance.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"\nWritten: {out_path}")
    print()
    print(md)
