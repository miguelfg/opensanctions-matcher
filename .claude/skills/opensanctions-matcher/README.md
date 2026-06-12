# opensanctions-matcher

A local CLI tool to screen targets against [OpenSanctions](https://www.opensanctions.org/) bulk datasets — no API key, no network call at search time. Uses SQLite FTS5 as the default search engine for ranked, token-aware results, with optional rapidfuzz approximate matching for transliterations and typos.

---

## Quick Start

```bash
pip install rapidfuzz          # optional, required for --fuzzy
python3 scripts/os_search.py \
    --dataset-dir ~/.local/share/opensanctions/il_mod_crypto \
    --targets "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"
```

On first run an FTS5 index is built automatically next to the dataset file. Subsequent runs are instant.

---

## Requirements

| Dependency | Required | Purpose |
|---|---|---|
| Python 3.10+ | Yes | Core runtime |
| `rapidfuzz` | No | `--fuzzy` approximate matching |
| `ripgrep` (`rg`) | No | Faster `--no-fts` grep fallback |

---

## Installation

```bash
git clone https://github.com/miguelfg/opensanctions-matcher.git
cd opensanctions-matcher
pip install rapidfuzz          # optional
```

No other install step is needed — `os_search.py` has no mandatory third-party dependencies.

---

## Usage

### Names-first two-phase search (default)

Searches `names.txt` first. Any hits are automatically enriched from `targets.simple.csv`.

```bash
python3 scripts/os_search.py \
    --dataset-dir /path/to/dataset \
    --targets "Alexei Navalny" "Gazprom"
```

### Search a specific file type

```bash
# Search the simple CSV directly
python3 scripts/os_search.py --dataset-dir /path/to/dataset \
    --file csv --targets "Hamas Finance Committee"

# Search the full FtM JSON
python3 scripts/os_search.py --dataset-dir /path/to/dataset \
    --file ftm --targets "Vladimir Putin" --schema Person
```

### Fuzzy matching

Runs after FTS5 and surfaces approximate hits FTS5 missed (transliterations, typos, OCR noise).

```bash
# Default threshold 80
python3 scripts/os_search.py --dataset-dir /path/to/dataset \
    --targets "Aleksei Navalnyy" --fuzzy

# Custom threshold (0–100)
python3 scripts/os_search.py --dataset-dir /path/to/dataset \
    --targets "Aleksei Navalnyy" --fuzzy 65
```

### Targets from a file

```bash
python3 scripts/os_search.py --dataset-dir /path/to/dataset \
    --targets-file wallets.txt
```

### Flag reference

| Flag | Default | Description |
|---|---|---|
| `--dataset-dir DIR` | — | Directory containing the dataset files |
| `--dataset PATH` | — | Path to `entities.ftm.json` (legacy, implies `--file ftm`) |
| `--file {names,csv,ftm}` | `names` | Which dataset file to search |
| `--targets TARGET [...]` | — | One or more target strings |
| `--targets-file FILE` | — | File with one target per line |
| `--schema SCHEMA` | — | Filter by FtM schema (`--file ftm` only) |
| `--fuzzy [THRESHOLD]` | disabled | Enable fuzzy matching; threshold defaults to `80` |
| `--no-fts` | off | Disable FTS5 index; use original grep/substring search |
| `--no-holder-lookup` | off | Skip holder entity lookups (`--file ftm` only) |

---

## How It Works

### FTS5 index lifecycle

On first search against a dataset file, `os_search.py` builds a SQLite FTS5 index (`.fts5.db`) next to the source file. The index is rebuilt automatically whenever the source file is newer than the index — no manual cache management needed. Pass `--no-fts` to skip the index entirely and fall back to the original grep path.

### Query strategy

| Target pattern | FTS5 query | Rationale |
|---|---|---|
| Multi-word (`"Vladimir Putin"`) | `"vladimir putin"` | Phrase search — tokens must appear in sequence |
| Single word (`"Gazprom"`) | `gazprom OR gazprom*` | Exact token plus prefix — catches partial inputs |
| Crypto address (≥ 20 alnum chars) | exact token | Single-token exact match |

Results are ranked by BM25 and deduplicated by entity `id`.

### Fuzzy layer

When `--fuzzy` is active, a second pass runs `rapidfuzz.process.extract` with the WRatio scorer over all indexed captions. Only hits not already returned by FTS5 are included, labelled `⚠️  FUZZY MATCH`.

---

## Supported Dataset File Types

| File | Indexed columns | Output |
|---|---|---|
| `names.txt` | `name` | Matched lines |
| `targets.simple.csv` | `caption`, `aliases`, `identifiers` | Full CSV row as dict |
| `entities.ftm.json` | `caption`, `names`, `aliases`, `identifiers` | Parsed FtM entity with all properties |

---

## Output Format

```
============================================================
OpenSanctions Search
  Dataset : il_mod_crypto
  File    : names.txt
  Targets : 1
============================================================

── Searching: TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy
  ✅ FTS MATCH (1 line(s))
  Matched : TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy
  Web URL : https://www.opensanctions.org/search/?scope=il_mod_crypto&q=...

── Phase 2: enriching 1 hit(s) from targets.simple.csv

  Enrichment for TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy (match 1):
  ...

── Searching: Aleksei Navalnyy   (with --fuzzy 70)
  ⚠️  FUZZY MATCH (score: 87) — Alexei Navalny
```

Exit code `0` when at least one match is found; `2` when no matches.

---

## License

See [LICENSE](LICENSE).
