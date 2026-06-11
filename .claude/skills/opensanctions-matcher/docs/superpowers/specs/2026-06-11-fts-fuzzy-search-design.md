# FTS5 + Fuzzy Search Design

**Date:** 2026-06-11
**Status:** approved
**Scope:** `os_search.py` — replace grep/substring matching with SQLite FTS5 as default, add optional rapidfuzz fuzzy layer

---

## Problem

Current search is case-insensitive substring grep (`rg -i -F` / `grep -i -F`). This has two limitations:

1. **No ranking or token awareness** — `grep -F "Putin"` matches `Vladimir Putin` and `Computin` equally; no way to distinguish token boundaries
2. **No approximate matching** — transliterations, typos, and spelling variants produce zero results

---

## Solution

Replace grep with SQLite FTS5 as the default search engine. Add `--fuzzy [threshold]` to layer rapidfuzz on top for approximate matching. Keep `--no-fts` as a full backward-compatibility escape hatch.

---

## Index Structure

One SQLite file per source file, co-located with the source:

| Source file | Index file |
|---|---|
| `names.txt` | `names.txt.fts5.db` |
| `targets.simple.csv` | `targets.simple.csv.fts5.db` |
| `entities.ftm.json` | `entities.ftm.json.fts5.db` |

All tables use `tokenize='unicode61'` (accent folding, case-insensitive, alphanumeric wallet addresses treated as single tokens).

### names.txt index

```sql
CREATE VIRTUAL TABLE names USING fts5(
    name,
    tokenize='unicode61'
);
```

One row per non-blank, non-comment line.

### targets.simple.csv index

```sql
CREATE VIRTUAL TABLE entities USING fts5(
    id        UNINDEXED,
    caption,
    aliases,
    identifiers,
    raw_row   UNINDEXED,
    tokenize='unicode61'
);
```

`id` and `raw_row` are stored but not tokenised. `raw_row` holds the full CSV line for display without a second file scan.

### entities.ftm.json index

```sql
CREATE VIRTUAL TABLE entities USING fts5(
    id        UNINDEXED,
    caption,
    names,
    aliases,
    raw_json  UNINDEXED,
    tokenize='unicode61'
);
```

`names` = `properties.name[]` joined with spaces. `aliases` = `properties.alias[]` joined with spaces. `raw_json` holds the full JSON line for display.

---

## Index Lifecycle

**Build trigger:** index is built (or rebuilt) when:
- `.fts5.db` does not exist, OR
- source file mtime > index file mtime

**Build is transparent:** happens inside `os_search.py` before search runs. One status line printed:
```
[info] Building FTS index for names.txt (first run or dataset updated)...
```

**Build strategy:**
- Single transaction, batched inserts (1 000 rows/batch) for speed
- For `entities.ftm.json`, print progress every 100 000 rows
- On rebuild: delete old `.fts5.db` first, recreate atomically — no partial index on error

**Bypass:** `--no-fts` skips index check and build entirely, falls back to original grep/Python path.

---

## FTS5 Query Strategy

For each target string:

| Case | FTS5 query | Rationale |
|---|---|---|
| Multi-word (`"Vladimir Putin"`) | `"vladimir putin"` | Phrase search — tokens must appear in sequence |
| Single word (`"Gazprom"`) | `gazprom OR gazprom*` | Exact token OR prefix — catches partial inputs like `Gaz` |
| Crypto address (`"0xABC123"`) | `0xABC123` | Single alphanumeric token, exact match sufficient |

`fts_query()` detects the single-word vs. multi-word case by checking for spaces in the target. A target is treated as a crypto address (exact only, no prefix suffix) when it is a single token of ≥ 20 alphanumeric characters — covers Bitcoin, Ethereum, Tron, and similar address formats.

Results are ranked by BM25. Deduplicated by entity `id` across all indexed columns. Output label changes from `✅ NAMES MATCH` to `✅ FTS MATCH`.

---

## Fuzzy Layer

**Activation:** `--fuzzy [THRESHOLD]`
- `--fuzzy` alone → threshold defaults to `80`
- `--fuzzy 75` → explicit threshold
- Range: 0–100 (WRatio score)

**Algorithm:**

1. FTS5 runs first and collects its hits (set A)
2. Fuzzy pass: `SELECT` all indexed text terms from `.fts5.db`
3. `rapidfuzz.process.extract(target, choices, scorer=WRatio, score_cutoff=threshold)`
4. Map matched terms back to rows via `rowid` or `id`
5. Deduplicate against set A — only new hits are added as fuzzy results

**Output label for fuzzy-only hits:**
```
⚠️  FUZZY MATCH (score: 87) — Vladimyr Pootin
```

**Performance warning:** when `--fuzzy` is used against a large dataset (> 500 000 entries), the script prints:
```
[warn] Fuzzy scan on large dataset (N entries) — this may take a moment
```

---

## CLI Changes

Two new flags added to `os_search.py`:

```
--fuzzy [THRESHOLD]   Enable fuzzy matching via rapidfuzz WRatio (default threshold: 80).
                      Runs after FTS5; surfaces approximate matches FTS5 missed.

--no-fts              Disable FTS5 index, use original grep/substring search.
                      Useful for debugging or when rapidfuzz is unavailable.
```

All existing flags (`--dataset`, `--dataset-dir`, `--file`, `--targets`, `--targets-file`, `--schema`, `--no-holder-lookup`) are unchanged.

---

## Code Architecture

### New functions

| Function | Purpose |
|---|---|
| `get_index_path(source: Path) -> Path` | Returns `source.fts5.db` path |
| `index_is_stale(source: Path, index: Path) -> bool` | Compares mtime |
| `build_names_index(source: Path, index: Path)` | Builds FTS5 for names.txt |
| `build_csv_index(source: Path, index: Path)` | Builds FTS5 for targets.simple.csv |
| `build_ftm_index(source: Path, index: Path)` | Builds FTS5 for entities.ftm.json |
| `ensure_index(source: Path, file_type: str)` | Top-level: check staleness, dispatch to builder |
| `fts_query(target: str) -> str` | Builds the FTS5 MATCH expression |
| `search_fts_names(index: Path, target: str) -> list[str]` | Returns matched name strings |
| `search_fts_csv(index: Path, target: str) -> list[dict]` | Returns matched row dicts |
| `search_fts_ftm(index: Path, target: str) -> list[dict]` | Returns matched entity dicts |
| `search_fuzzy(index: Path, target: str, threshold: int, file_type: str) -> list` | rapidfuzz scan, returns new hits only |

### Modified functions

| Function | Change |
|---|---|
| `search_names_txt` | When FTS available: delegates to `search_fts_names`; `--no-fts` keeps existing path |
| `search_csv` | When FTS available: delegates to `search_fts_csv`; `--no-fts` keeps existing path |
| `search_target` (FtM) | When FTS available: delegates to `search_fts_ftm`; `--no-fts` keeps existing path |
| `main` | Adds `--fuzzy`, `--no-fts` args; calls `ensure_index` before search when FTS active |

---

## Dependencies

- `sqlite3` — stdlib, no install needed
- `rapidfuzz` — required only when `--fuzzy` is used; import is deferred, prints actionable error if missing:
  ```
  [error] --fuzzy requires rapidfuzz: pip install rapidfuzz
  ```

---

## Out of Scope

- Phonetic matching (Soundex, Metaphone) — not in this iteration
- Multi-language transliteration — handled implicitly by unicode61 accent folding
- Remote/API search — this skill is local-only by design
- Index compression or encryption
