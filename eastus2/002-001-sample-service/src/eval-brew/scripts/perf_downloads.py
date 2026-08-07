"""Download builder performance benchmark.

Measures wall-clock time and output size for all four download builders
(CSV, XLSX, Flat CSV, Flat XLSX) across two data profiles:

  Baseline : 2 dimensions, ~11-word reasoning, 3 sources × ~28-word chunk
  Heavy    : 4 dimensions, 30-word reasoning,  3 sources × 300-word chunk

Utterance counts: 250 / 500 / 750 / 1000 / 2000.

Run from the repo root with the virtualenv active:
    python scripts/perf_downloads.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "src"))

from harness.ui.detail.view import (
    results_csv_builder,
    results_flat_csv_builder,
    results_flat_xlsx_builder,
    results_xlsx_builder,
)

# ── Prose constants ───────────────────────────────────────────────────────────

# ~30 words
_REASONING_30W = (
    "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod "
    "tempor incididunt ut labore et dolore magna aliqua ut enim ad minim "
    "veniam quis nostrud exercitation ullamco laboris."
)

# ~300 words — 10 repetitions of the 30-word phrase above
_CHUNK_300W = (_REASONING_30W + " ") * 10

# ── Profile definitions ───────────────────────────────────────────────────────

def _profile_baseline():
    """2 dims, ~11-word reasoning, 3 sources × ~28-word chunk."""
    sources = [
        {
            "url": f"https://kb.example.com/article-{i}",
            "title": f"KB Article {i}: How to configure the system",
            "chunk": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 4,
            "scope": "hr-policy",
            "documentId": f"doc-{i:04d}",
        }
        for i in range(1, 4)
    ]
    scores = [
        {"parameter_name": "relevance", "score": 0.87, "verdict": "pass",
         "reasoning": "The response directly addresses the user question with accurate detail."},
        {"parameter_name": "tone", "score": 0.74, "verdict": "warn",
         "reasoning": "Tone is mostly appropriate but slightly formal for the context."},
    ]
    return sources, scores


def _profile_heavy():
    """4 dims, 30-word reasoning, 3 sources × 300-word chunk."""
    sources = [
        {
            "url": f"https://kb.example.com/article-{i}",
            "title": f"KB Article {i}: How to configure the enterprise HR system",
            "chunk": _CHUNK_300W,
            "scope": "hr-policy",
            "documentId": f"doc-{i:04d}",
        }
        for i in range(1, 4)
    ]
    scores = [
        {"parameter_name": dim, "score": round(0.6 + i * 0.1, 1), "verdict": "pass",
         "reasoning": _REASONING_30W}
        for i, dim in enumerate(["relevance", "tone", "accuracy", "completeness"])
    ]
    return sources, scores


def _make_utterances(n: int, sources, scores):
    contract = {
        "chatbotResponse": {
            "normalizedText": (
                "Thank you for your question. Based on our HR policy documents, "
                "the answer is as follows: employees are entitled to 20 days of "
                "annual leave per calendar year, accrued monthly."
            ),
            "metadata": {"sources": sources},
        }
    }

    class _Result:
        normalized_contract = contract
        evaluation_verdict = "pass"
        evaluation_scores = scores
        utterance_intent = "hr-faq"
        error_status = None
        error_stage = None

    rows = []
    for i in range(n):
        class _U:
            utterance_id = f"uid-{i:06d}"
            row_index = i + 1
            utterance_text = f"What is the annual leave policy? (row {i + 1})"
            test_id = f"T{(i % 20) + 1:03d}"
            extra_metadata = {}
            evaluation_result = _Result()
        _U.__name__ = f"U{i}"
        rows.append(_U())
    return rows


class _FakeJob:
    job_id = "perf-test-job-0001"
    source_csv_filename = "perf_test.csv"


# ── Benchmark runner ──────────────────────────────────────────────────────────

COUNTS = [250, 500, 750, 1000, 2000]
RUNS = 3

BUILDERS = [
    ("CSV (long format)",  results_csv_builder),
    ("XLSX (long format)", results_xlsx_builder),
    ("Flat CSV",           results_flat_csv_builder),
    ("Flat XLSX",          results_flat_xlsx_builder),
]


def _bench(fn, job, utterances) -> tuple[float, int]:
    times = []
    size = 0
    for _ in range(RUNS):
        t0 = time.perf_counter()
        _, out = fn(job, utterances)
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        size = len(out.encode("utf-8") if isinstance(out, str) else out)
    return sum(times) / len(times), size


def run_profile(sources, scores, label: str) -> list[dict]:
    job = _FakeJob()
    rows = []
    for n in COUNTS:
        print(f"  [{label}] n={n:4d} ...", end=" ", flush=True)
        utterances = _make_utterances(n, sources, scores)
        for fmt_label, fn in BUILDERS:
            avg, size = _bench(fn, job, utterances)
            rows.append({"profile": label, "n": n, "format": fmt_label,
                         "elapsed_s": avg, "size_bytes": size})
            print(".", end="", flush=True)
        print()
    return rows


# ── Markdown output ───────────────────────────────────────────────────────────

def _fmt_ms(s: float) -> str:
    ms = s * 1000
    if ms >= 1000:
        return f"{ms / 1000:.2f} s"
    return f"{ms:.0f} ms"


def _fmt_size(b: int) -> str:
    if b >= 1_048_576:
        return f"{b / 1_048_576:.1f} MB"
    return f"{b / 1024:.0f} KB"


def _row_expansion(profile: str, format_name: str) -> str:
    if "long" in format_name.lower():
        dims = 4 if profile == "Heavy" else 2
        return f"{dims} dims × 3 src = {dims * 3} rows/utterance"
    else:
        dims = 4 if profile == "Heavy" else 2
        fixed = 5
        dim_cols = dims * 3
        src_cols = 3 * 5
        return f"{fixed} + {dim_cols} dim + {src_cols} src = {fixed + dim_cols + src_cols} cols"


def build_markdown(baseline_rows: list[dict], heavy_rows: list[dict]) -> str:
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
        f"**Method:** avg of {RUNS} runs per cell, builders called directly (no HTTP overhead)",
        "",
        "---",
        "",
        "## Profile A — Baseline",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        "| Dimensions | 2 (relevance, tone) |",
        "| Reasoning per dimension | ~11 words |",
        "| Sources per utterance | 3 |",
        "| Chunk length per source | ~28 words |",
        "| Long-format row expansion | 2 dims × 3 sources = **6 rows/utterance** |",
        "| Flat column count | 5 fixed + 6 dim + 15 src = **26 columns** |",
        "",
        "| Utterances | Format | Avg time | File size |",
        "|:----------:|:-------|:--------:|----------:|",
    ]
    for r in baseline_rows:
        lines.append(
            f"| {r['n']:>10,} | {r['format']:<20} | {_fmt_ms(r['elapsed_s']):>8} "
            f"| {_fmt_size(r['size_bytes']):>9} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Profile B — Heavy (4 dims · 30-word reasoning · 300-word chunks)",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        "| Dimensions | 4 (relevance, tone, accuracy, completeness) |",
        "| Reasoning per dimension | 30 words |",
        "| Sources per utterance | 3 |",
        "| Chunk length per source | 300 words |",
        "| Long-format row expansion | 4 dims × 3 sources = **12 rows/utterance** |",
        "| Flat column count | 5 fixed + 12 dim + 15 src = **32 columns** |",
        "",
        "| Utterances | Format | Avg time | File size |",
        "|:----------:|:-------|:--------:|----------:|",
    ]
    for r in heavy_rows:
        lines.append(
            f"| {r['n']:>10,} | {r['format']:<20} | {_fmt_ms(r['elapsed_s']):>8} "
            f"| {_fmt_size(r['size_bytes']):>9} |"
        )

    # Growth rates from the heavy profile (1000 → 2000)
    heavy_2000 = {r["format"]: r for r in heavy_rows if r["n"] == 2000}
    heavy_1000 = {r["format"]: r for r in heavy_rows if r["n"] == 1000}

    lines += [
        "",
        "---",
        "",
        "## Scaling analysis (Profile B, 1000 → 2000 utterances)",
        "",
        "| Format | Time ×factor | Size ×factor |",
        "|:-------|:------------:|:------------:|",
    ]
    for fmt_label, _ in BUILDERS:
        r2 = heavy_2000[fmt_label]
        r1 = heavy_1000[fmt_label]
        tf = r2["elapsed_s"] / r1["elapsed_s"] if r1["elapsed_s"] else 0
        sf = r2["size_bytes"] / r1["size_bytes"] if r1["size_bytes"] else 0
        lines.append(f"| {fmt_label:<20} | {tf:.2f}× | {sf:.2f}× |")

    lines += [
        "",
        "---",
        "",
        "## Notes",
        "",
        "- **Long-format** (CSV and XLSX): one row per *(utterance × dimension × source)*.",
        "  Profile A: 6 rows/utterance. Profile B: 12 rows/utterance.",
        "- **Flat** (CSV and XLSX): one row per utterance with all dims and sources as columns.",
        "  Profile B flat CSV is typically 50–60× smaller than long-format CSV at the same count",
        "  because each chunk appears once (flat) vs 4× (long, once per dimension).",
        "- **XLSX** uses `write_only=True` (openpyxl streaming), keeping RAM proportional to one",
        "  row regardless of total count.",
        "- **ZIP compression** in XLSX benefits from repetitive text; the 300-word chunks are",
        "  identical across all utterances in this synthetic benchmark. Real data will compress",
        "  less well, so treat XLSX sizes as a lower bound.",
        "- **CSV sizes** reflect uncompressed UTF-8 text; real transfer sizes depend on",
        "  whether the HTTP layer applies gzip (which it does not for file downloads by default).",
        "",
    ]

    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Running {RUNS} reps x {len(COUNTS)} counts x 4 formats x 2 profiles ...\n")

    print("Profile A: Baseline")
    baseline_rows = run_profile(*_profile_baseline(), label="Baseline")

    print("\nProfile B: Heavy (4 dims, 30-word reasoning, 300-word chunks)")
    heavy_rows = run_profile(*_profile_heavy(), label="Heavy")

    md = build_markdown(baseline_rows, heavy_rows)

    out_path = _root / "docs" / "tests" / "download-performance.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"\nWritten: {out_path}\n")
    print(md.encode("ascii", errors="replace").decode("ascii"))
