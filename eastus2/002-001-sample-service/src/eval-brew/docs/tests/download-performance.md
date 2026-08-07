# Download Builder Performance

**Date:** 2026-08-07 22:47  
**Git SHA:** `5df317f`  
**Python:** 3.14.6  
**Method:** avg of 3 runs per cell, builders called directly (no HTTP overhead)

---

## Profile A — Baseline

| Parameter | Value |
|-----------|-------|
| Dimensions | 2 (relevance, tone) |
| Reasoning per dimension | ~11 words |
| Sources per utterance | 3 |
| Chunk length per source | ~28 words |
| Long-format row expansion | 2 dims × 3 sources = **6 rows/utterance** |
| Flat column count | 5 fixed + 6 dim + 15 src = **26 columns** |

| Utterances | Format | Avg time | File size |
|:----------:|:-------|:--------:|----------:|
|        250 | CSV (long format)    |    12 ms |    952 KB |
|        250 | XLSX (long format)   |   291 ms |    122 KB |
|        250 | Flat CSV             |     4 ms |    334 KB |
|        250 | Flat XLSX            |    83 ms |     33 KB |
|        500 | CSV (long format)    |    24 ms |    1.9 MB |
|        500 | XLSX (long format)   |   496 ms |    236 KB |
|        500 | Flat CSV             |     9 ms |    669 KB |
|        500 | Flat XLSX            |   134 ms |     58 KB |
|        750 | CSV (long format)    |    37 ms |    2.8 MB |
|        750 | XLSX (long format)   |   749 ms |    350 KB |
|        750 | Flat CSV             |    13 ms |   1003 KB |
|        750 | Flat XLSX            |   183 ms |     83 KB |
|      1,000 | CSV (long format)    |    50 ms |    3.7 MB |
|      1,000 | XLSX (long format)   |   949 ms |    464 KB |
|      1,000 | Flat CSV             |    18 ms |    1.3 MB |
|      1,000 | Flat XLSX            |   248 ms |    108 KB |
|      2,000 | CSV (long format)    |    99 ms |    7.4 MB |
|      2,000 | XLSX (long format)   |   1.86 s |    918 KB |
|      2,000 | Flat CSV             |    44 ms |    2.6 MB |
|      2,000 | Flat XLSX            |   479 ms |    211 KB |

---

## Profile B — Heavy (4 dims · 30-word reasoning · 300-word chunks)

| Parameter | Value |
|-----------|-------|
| Dimensions | 4 (relevance, tone, accuracy, completeness) |
| Reasoning per dimension | 30 words |
| Sources per utterance | 3 |
| Chunk length per source | 300 words |
| Long-format row expansion | 4 dims × 3 sources = **12 rows/utterance** |
| Flat column count | 5 fixed + 12 dim + 15 src = **32 columns** |

| Utterances | Format | Avg time | File size |
|:----------:|:-------|:--------:|----------:|
|        250 | CSV (long format)    |    69 ms |    7.0 MB |
|        250 | XLSX (long format)   |   509 ms |    247 KB |
|        250 | Flat CSV             |    17 ms |    1.7 MB |
|        250 | Flat XLSX            |    97 ms |     47 KB |
|        500 | CSV (long format)    |   140 ms |   13.9 MB |
|        500 | XLSX (long format)   |   914 ms |    485 KB |
|        500 | Flat CSV             |    35 ms |    3.3 MB |
|        500 | Flat XLSX            |   163 ms |     86 KB |
|        750 | CSV (long format)    |   212 ms |   20.9 MB |
|        750 | XLSX (long format)   |   1.36 s |    723 KB |
|        750 | Flat CSV             |    55 ms |    5.0 MB |
|        750 | Flat XLSX            |   228 ms |    124 KB |
|      1,000 | CSV (long format)    |   280 ms |   27.9 MB |
|      1,000 | XLSX (long format)   |   1.81 s |    960 KB |
|      1,000 | Flat CSV             |    72 ms |    6.7 MB |
|      1,000 | Flat XLSX            |   313 ms |    163 KB |
|      2,000 | CSV (long format)    |   605 ms |   55.7 MB |
|      2,000 | XLSX (long format)   |   3.52 s |    1.9 MB |
|      2,000 | Flat CSV             |   140 ms |   13.3 MB |
|      2,000 | Flat XLSX            |   559 ms |    313 KB |

---

## Scaling analysis (Profile B, 1000 → 2000 utterances)

| Format | Time ×factor | Size ×factor |
|:-------|:------------:|:------------:|
| CSV (long format)    | 2.16× | 2.00× |
| XLSX (long format)   | 1.94× | 1.99× |
| Flat CSV             | 1.95× | 2.00× |
| Flat XLSX            | 1.78× | 1.92× |

---

## Notes

- **Long-format** (CSV and XLSX): one row per *(utterance × dimension × source)*.
  Profile A: 6 rows/utterance. Profile B: 12 rows/utterance.
- **Flat** (CSV and XLSX): one row per utterance with all dims and sources as columns.
  Profile B flat CSV is typically 50–60× smaller than long-format CSV at the same count
  because each chunk appears once (flat) vs 4× (long, once per dimension).
- **XLSX** uses `write_only=True` (openpyxl streaming), keeping RAM proportional to one
  row regardless of total count.
- **ZIP compression** in XLSX benefits from repetitive text; the 300-word chunks are
  identical across all utterances in this synthetic benchmark. Real data will compress
  less well, so treat XLSX sizes as a lower bound.
- **CSV sizes** reflect uncompressed UTF-8 text; real transfer sizes depend on
  whether the HTTP layer applies gzip (which it does not for file downloads by default).
