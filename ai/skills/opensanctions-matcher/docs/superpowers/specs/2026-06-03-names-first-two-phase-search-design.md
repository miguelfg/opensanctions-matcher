# OpenSanctions Skill — Names-First Two-Phase Search

**Date:** 2026-06-03  
**Status:** Approved  
**Scope:** `opensanctions-search` skill — `SKILL.md` + `scripts/os_search.py`

---

## Problem

The skill currently defaults to downloading `entities.ftm.json` as its first step. For most
datasets this file is 1–5 MB (and for large collections 300–700 MB). The `names.txt` file
contains the same target strings at ~150× smaller size (15 KB for `il_mod_crypto`), making
it the correct first screening step before committing to a larger download.

---

## Goal

1. Default to `names.txt` for the initial screen — fast, tiny download.
2. Auto-enrich on a hit by fetching `targets.simple.csv` (421 KB) and re-searching matched
   targets to surface entity properties.
3. Surface an OpenSanctions web URL for every hit so the user can explore interactively.
4. Keep `entities.ftm.json` available as an explicit opt-in for full FtM detail.
5. Preserve 100% backwards compatibility with existing `--dataset path/to/entities.ftm.json`
   call sites.

---

## File Hierarchy

```
~/.local/share/opensanctions/<dataset>/
  names.txt               phase 1 — 15 KB  (default)
  targets.simple.csv      phase 2 — 421 KB (auto on hit)
  entities.ftm.json       phase 3 — 2+ MB  (opt-in, existing behaviour)
```

Each file has an independent 7-day staleness check and download confirmation gate.

---

## `os_search.py` Changes

### New CLI flags

| Flag | Values | Default | Notes |
|---|---|---|---|
| `--file` | `names` \| `csv` \| `ftm` | `names` | Which file to search |
| `--dataset-dir` | path | — | Directory containing dataset files; `--dataset` still accepted for compat |

`--dataset path/to/entities.ftm.json` continues to work unchanged. The script detects the
`.ftm.json` suffix and routes to the FtM path, ignoring `--file`.

### New internal functions

| Function | Signature | Purpose |
|---|---|---|
| `search_names_txt` | `(path, targets, rg_bin) → dict[str, list[str]]` | Raw line search; returns `{target: [matched_lines]}` |
| `search_csv` | `(path, targets, rg_bin) → dict[str, list[dict]]` | rg pre-filter + `csv.DictReader`; returns `{target: [row_dicts]}` |
| `format_csv_entity` | `(row, dataset_name) → str` | Renders CSV row in same block style as `format_entity()` |
| `os_web_url` | `(dataset_name, target) → str` | Returns `https://www.opensanctions.org/search/?scope=<ds>&q=<encoded>` |

### Existing functions

`search_target()`, `format_entity()`, `grep_lines()`, `lookup_holder()` — **unchanged**.
The FtM path is untouched.

### `main()` routing

```
if --file names (default):
    phase1 = search_names_txt(names.txt, targets, rg_bin)
    print matched lines + web URL for each hit
    if any hits:
        download targets.simple.csv if not cached
        phase2 = search_csv(targets.simple.csv, hit_targets, rg_bin)
        print enriched CSV entity blocks
    else:
        suggest --file ftm or widen dataset

elif --file csv:
    search_csv(targets.simple.csv, targets, rg_bin) directly

elif --file ftm:
    existing FtM path (no change)
```

---

## SKILL.md Changes

- Steps 2–4: replace hardcoded `entities.ftm.json` with `<filename>` variable; default value
  is `names.txt`.
- Step 3 download confirmation: show size for the specific file being requested.
- Step 5: call `os_search.py --file names` (or `--dataset-dir`) by default.
- Add **Step 5b**: describes two-phase output — Phase 1 name hits + web URL, Phase 2 CSV
  enrichment block, and the optional Phase 3 FtM deep-dive prompt.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `names.txt` has blank or `#` comment lines | Strip before matching |
| CSV missing expected columns | Skip missing columns; only `id` and `caption` required |
| Partial substring hit in `names.txt` | Print full matched line; Phase 2 provides verification |
| Phase 2 CSV download fails | Print web URL, exit non-zero |
| `rg` not available | Fall back to `grep -i -F` for all three file types |
| `--dataset path/to/entities.ftm.json` (legacy) | Detect `.ftm.json` suffix → route to FtM path, ignore `--file` |

---

## Output Format

### Phase 1 hit (names.txt)

```
── Searching: TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy
  ✅ NAMES MATCH (1 line)
  Matched : TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy
  Web URL : https://www.opensanctions.org/search/?scope=il_mod_crypto&q=TUFXua1q...
  → Fetching targets.simple.csv for enrichment…
```

### Phase 2 enrichment (targets.simple.csv)

```
  Schema    : CryptoWallet
  Caption   : <caption from csv>
  ID        : <id>
  Topics    : 🔴 SANCTION
  Datasets  : il_mod_crypto
  Seen      : 2024-01-01 → 2026-04-17
```

### No match

```
  ❌ NO MATCH in names.txt
  Consider: os_search.py --file ftm  (downloads entities.ftm.json, ~2.4 MB)
```

---

## What Is Not Changing

- Dataset selection table in SKILL.md (which dataset to pick for which target type)
- Cache directory location (`~/.local/share/opensanctions/`)
- 7-day staleness threshold
- Interactive download confirmation gate
- FtM entity formatting and holder lookup
- `--targets`, `--targets-file`, `--schema`, `--no-holder-lookup` flags
