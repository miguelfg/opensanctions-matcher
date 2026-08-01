# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands run from `ai/skills/opensanctions-matcher/`.

```bash
# Run full test suite
cd ai/skills/opensanctions-matcher && python -m pytest scripts/tests/test_os_search.py -v

# Run a single test by name
python -m pytest scripts/tests/test_os_search.py -k "test_search_fuzzy_names_finds_approximate" -v

# Run the CLI directly
python3 scripts/os_search.py --dataset-dir ~/.local/share/opensanctions/<dataset_name> --targets "TARGET"

# Run with fuzzy matching
python3 scripts/os_search.py --dataset-dir ~/.local/share/opensanctions/<dataset_name> --targets "NAME" --fuzzy 75

# Fall back to grep (no FTS index)
python3 scripts/os_search.py --dataset-dir ~/.local/share/opensanctions/<dataset_name> --targets "TARGET" --no-fts

# Versioning helpers
make version
make check-version
make bump-patch    # or bump-minor / bump-major
make bump-dry-run  # inspect the next version without changing files
make release-patch # also prep changelog, commit, tag, and push
```

## Architecture

The skill lives entirely under `ai/skills/opensanctions-matcher/`. The only executable source is `scripts/os_search.py`; everything else is documentation or test infrastructure.

### Search pipeline

Three independent file-type paths share a common FTS5 index layer:

```
main()
├── --file ftm   → search_target()     → search_fts_ftm() / grep fallback
├── --file csv   → search_csv()        → search_fts_csv() / grep fallback
└── --file names → search_names_txt()  → search_fts_names() / substring fallback
                   └── Phase 2: auto-enriches hits via search_csv() on targets.simple.csv
```

Each path has a `use_fts: bool = True` parameter that switches between FTS5 and the original grep/substring fallback. The CLI flag `--no-fts` sets `use_fts=False` across all call sites.

### FTS5 index layer

- **Index location:** `<source_file>.fts5.db` co-located with the dataset file
- **Staleness check:** `index_is_stale()` compares source vs. index mtime; `ensure_index()` rebuilds transparently on first run or after dataset update
- **Three index schemas:**
  - `names.txt` → `fts5(name)` — one name per row
  - `targets.simple.csv` → `fts5(id UNINDEXED, caption, aliases, identifiers, raw_row UNINDEXED)`
  - `entities.ftm.json` → `fts5(id UNINDEXED, caption, names, aliases, identifiers, raw_json UNINDEXED)`
- **Query strategy in `fts_query()`:** phrase search for multi-word targets; exact match for crypto addresses (≥20 alnum chars); `word OR word*` prefix for short single tokens

### Fuzzy matching

`search_fuzzy(index, target, threshold, file_type, existing_ids)` runs **after** FTS and deduplicates against FTS results via `existing_ids`. Enabled with `--fuzzy [THRESHOLD]` (default 80). Requires `rapidfuzz` (imported lazily; prints install hint on `ImportError`). Silently disabled when `--no-fts` is active. Results carry `_fuzzy_score`; names results also carry `_fuzzy_match`.

### Output / exit codes

- FTS hits → label `FTS MATCH`; `--no-fts` hits → label `NAMES MATCH`; fuzzy hits → label `⚠️  Fuzzy Match N (score: S)`
- Exit `0` = at least one hit, `2` = no matches, `1` = argument error

### Skill workflow (SKILL.md)

The AI skill wraps the CLI in a 6-step workflow: classify target type → check local cache at `~/.local/share/opensanctions/` → fetch size from dataset index JSON → ask user to confirm download → run `os_search.py` → interpret results using `references/ftm-schema.md`. Dataset selection table is in `SKILL.md` Step 1; full catalogue is in `references/datasets.md`.

## Key conventions

- All three FTS5 index builders use `unicode61` tokenizer and batch inserts (1000 rows/batch)
- `parse_entity(line)` is the single JSON-parse entry point for FtM NDJSON lines; returns `None` on decode error
- `prop(entity, key)` safely extracts `entity["properties"][key]` as a list
- The `identifiers` FTS5 column indexes `publicKey`, `ibanNumber`, `registrationNumber`, `taxNumber`, `passportNumber`, `idNumber` — extend this list when new FtM property types need to be searchable
- Test fixtures are static files in `scripts/tests/fixtures/`; `dataset_dir` fixture copies all three into a `tmp_path`
