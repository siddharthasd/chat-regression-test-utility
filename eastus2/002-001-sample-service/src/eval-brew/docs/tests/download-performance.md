# Download Builder Performance

**Date:** 2026-08-07 22:39  
**Git SHA:** `0062f3b`  
**Python:** 3.14.6  
**Profile:** 2 dimensions (relevance + tone), 3 KB sources per utterance  
**Method:** avg of 3 runs per cell, builders called directly (no HTTP overhead)

## Results

| Utterances | Format | Avg time | File size |
|:----------:|:-------|:--------:|----------:|
|        250 | CSV (long format)    |    10 ms |    952 KB |
|        250 | XLSX (long format)   |   314 ms |    122 KB |
|        250 | Flat CSV             |     4 ms |    334 KB |
|        250 | Flat XLSX            |    89 ms |     33 KB |
|        500 | CSV (long format)    |    21 ms |    1.9 MB |
|        500 | XLSX (long format)   |   520 ms |    236 KB |
|        500 | Flat CSV             |     9 ms |    669 KB |
|        500 | Flat XLSX            |   136 ms |     58 KB |
|        750 | CSV (long format)    |    33 ms |    2.8 MB |
|        750 | XLSX (long format)   |   763 ms |    350 KB |
|        750 | Flat CSV             |    13 ms |   1003 KB |
|        750 | Flat XLSX            |   192 ms |     83 KB |
|      1,000 | CSV (long format)    |    44 ms |    3.7 MB |
|      1,000 | XLSX (long format)   |   998 ms |    464 KB |
|      1,000 | Flat CSV             |    18 ms |    1.3 MB |
|      1,000 | Flat XLSX            |   242 ms |    108 KB |

## Notes

- **Long-format** builders produce one row per *(utterance × dimension × source)*.
  At 2 dims × 3 sources, each utterance expands to 6 rows.
- **Flat** builders produce one row per utterance with dynamic columns.
  Column count = 5 fixed + 6 dim cols (2 × 3) + 15 source cols (3 × 5) = 26 columns.
- XLSX builders use `write_only=True` (openpyxl streaming mode), which avoids holding
  cell objects in RAM and keeps memory usage roughly proportional to a single row.
- File sizes grow linearly with utterance count; the XLSX ZIP compression ratio
  improves as repetition increases, so per-row cost decreases at higher counts.
