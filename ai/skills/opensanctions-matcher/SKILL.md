---
name: opensanctions-matcher
version: 1.0.0
description: "Cross-check one or more targets (crypto wallet addresses, person names,
  companies, vessels, IBANs) against OpenSanctions bulk datasets downloaded locally.
  Automatically selects the most relevant dataset for the target type, interactively
  confirms before downloading if not cached, searches with a bundled Python script
  (SQLite FTS5 index, optional fuzzy matching for misspelt names), and returns a structured summary of matches with full FtM entity context. Use when a
  user wants to check whether a wallet address, person, organisation, or identifier
  appears on any sanctions list, ransomware tracker, PEP register, or watchlist.
  Triggers on: check sanctions, cross-check against OpenSanctions, is this wallet
  sanctioned, screen this address, OFAC check, sanctions lookup."
license: MIT
compatibility: "OpenSanctions data is CC BY-NC 4.0: free for non-commercial use; commercial use requires an OpenSanctions data license."
---

# OpenSanctions Search Skill

## Purpose

Screen one or more investigative targets against OpenSanctions bulk data. The skill
handles dataset selection, interactive download confirmation, fast local search via
a SQLite FTS5 index (with optional fuzzy matching), and structured result interpretation using the FtM schema.

Reference files:
- `references/datasets.md` — full dataset catalogue with names, descriptions, sizes
- `references/ftm-schema.md` — FtM entity types and property definitions

---

## Versioning

Current skill version: `1.0.0`.

Version bumps are managed from `ai/skills/opensanctions-matcher/` with `make bump-patch`, `make bump-minor`, or `make bump-major`. Those targets use `bumpversion` to update this file and `VERSION` together. For a full release, use `make release-patch`, `make release-minor`, or `make release-major`; those targets also prepend a changelog entry, commit, tag, and push.

---

## Workflow

### Step 1 — Classify Target and Select Dataset

Determine what the target is, then pick the narrowest dataset that covers it.

| Target type | Start with | Widen to if no hit |
|---|---|---|
| Crypto wallet (`0x…`, `bc1…`, `T…`, `1…`, `3…`) | `il_mod_crypto`, `us_fbi_lazarus_crypto`, `ransomwhere` | `sanctions` |
| US sanctions / OFAC | `us_ofac_sdn` | `sanctions` |
| EU sanctions | `eu_fsf` | `sanctions` |
| UN sanctions | `un_sc_sanctions` | `sanctions` |
| Ransomware payment address | `ransomwhere` | `crime` |
| Vessel / ship | `un_1718_vessels` | `maritime` |
| Company debarment | `debarment` | `default` |
| PEP / political figure | `peps` | `default` |
| Broad / unknown type | `default` (all-purpose, ~400 MB) | — |

When multiple targets of different types are provided, group them by type and run separate dataset searches.

Then pick the dataset file (`--file`) by target type:

| Target type | `--file` | Why |
|---|---|---|
| Person / company / vessel name | `names` (default) | `names.txt` holds names and aliases only |
| Crypto wallet, IBAN, passport, tax/registration number | `ftm` (or `csv`) | identifiers such as `publicKey` are only indexed in `entities.ftm.json` / `targets.simple.csv` |

Crypto datasets (`il_mod_crypto`, `us_fbi_lazarus_crypto`, `ransomwhere`) may not ship a `names.txt` at all — use `--file ftm`.

Consult `references/datasets.md` for the full catalogue of 353 available datasets.

---

### Step 2 — Check Local Cache

Default cache directory: `~/.local/share/opensanctions/`

```bash
ls -lh ~/.local/share/opensanctions/<dataset_name>/<filename> 2>/dev/null \
  && stat -c "%y" ~/.local/share/opensanctions/<dataset_name>/<filename>
```

Default file by phase:

| File | Phase | Typical size |
|---|---|---|
| `names.txt` | 1 — initial screen (default) | ~15 KB |
| `targets.simple.csv` | 2 — auto-enrichment on hit | ~420 KB |
| `entities.ftm.json` | 3 — full FtM detail (opt-in) | 1–5 MB |

- File present and **< 7 days old** → use as-is, skip download
- File present and **≥ 7 days old** → inform user the data is stale, offer to refresh
- File absent → proceed to Step 3

---

### Step 3 — Interactive Download Confirmation

Before downloading, fetch the file size from the dataset index and show the user:

```bash
curl -s "https://data.opensanctions.org/datasets/latest/<dataset_name>/index.json" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
target_file = 'names.txt'  # or targets.simple.csv / entities.ftm.json
for r in d.get('resources', []):
    if r.get('path', '').endswith(target_file) or r.get('name', '').endswith(target_file):
        size_mb = r.get('size', 0) / 1_048_576
        print(f\"  File : {r['title']}\")
        print(f\"  URL  : {r['url']}\")
        print(f\"  Size : {size_mb:.2f} MB\")
"
```

Then **ask the user to confirm** before downloading. Example:

> Dataset `il_mod_crypto` — names.txt (Target names text file)  
> Size: 0.02 MB | URL: https://data.opensanctions.org/…/names.txt  
> Download to `~/.local/share/opensanctions/il_mod_crypto/`? [y/N]

For collections (`sanctions`, `default`, `crime`, `peps`) that exceed 200 MB, add an explicit size warning.

---

### Step 4 — Download

After user confirms:

```bash
mkdir -p ~/.local/share/opensanctions/<dataset_name>
wget -q --show-progress \
  "<url_from_index>" \
  -O ~/.local/share/opensanctions/<dataset_name>/<filename>
```

Fallback if `wget` unavailable:

```bash
curl -L --progress-bar \
  "<url_from_index>" \
  -o ~/.local/share/opensanctions/<dataset_name>/<filename>
```

---

### Step 5 — Search

Run the bundled script for structured FtM-aware search and formatted output:

```bash
python3 <skill_dir>/scripts/os_search.py \
  --dataset-dir ~/.local/share/opensanctions/<dataset_name> \
  --targets "TARGET1" "TARGET2" \
  [--file names|csv|ftm] [--fuzzy [THRESHOLD]] [--schema CryptoWallet]
```

- `--file` — choose per Step 1 (default `names`; use `ftm` for wallets/identifiers)
- `--fuzzy [THRESHOLD]` — add approximate matches (default 80) for possibly misspelt or
  transliterated names; needs `pip install rapidfuzz`. Use it when an exact name search
  returns no match.
- `--schema` — filter FtM results by entity type (`--file ftm` only)
- `--no-fts` — fall back to `rg`/`grep` substring search (disables `--fuzzy`)

On first run the script builds a SQLite FTS5 index next to the dataset file
(`<file>.fts5.db`) and rebuilds it automatically when the dataset is refreshed.

Exit codes: `0` = at least one match, `2` = no matches, `1` = error (e.g. the chosen
`--file` is not in the dataset directory — download it or pick another `--file`).

Find `<skill_dir>` with: `find ~/.claude/skills ~/.local/share/claude-code/skills -name os_search.py 2>/dev/null | head -1`

---

### Step 5b — Two-Phase Output

With the default `--file names`, the script runs a two-phase pipeline.

**Phase 1 — `names.txt` screen:**

```
── Searching: Vladimir Putin
  ✅ FTS MATCH (1 line(s))
  Matched : Vladimir Putin
  Web URL : https://www.opensanctions.org/search/?scope=us_ofac_sdn&q=Vladimir+Putin

── Searching: Vladmir Putin            (misspelt, run with --fuzzy 75)
  ⚠️  FUZZY MATCH (score: 96) — Vladimir Putin
  ⚠️  FUZZY MATCH (score: 85) — Vladimir Vladimirovich Putin
```

Labels: `FTS MATCH` = index hit (`NAMES MATCH` with `--no-fts`); `⚠️ FUZZY MATCH (score: N)`
= approximate hit from `--fuzzy` — treat as a lead to verify, not a confirmed match.
With `--file ftm`/`csv`, hits print as `Match N:` (or `⚠️  Fuzzy Match N (score: S):`)
followed by the entity details.

**Phase 2 — `targets.simple.csv` enrichment (auto-triggered on any hit):**

If `targets.simple.csv` is cached in the dataset directory, the script fetches enriched properties automatically:

```
── Phase 2: enriching 1 hit(s) from targets.simple.csv

  Enrichment for TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy (match 1):
  Schema    : CryptoWallet
  Caption   : TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy
  ID        : Q123
  Topics    : 🔴 SANCTION
  Datasets  : il_mod_crypto
  Seen      : 2024-01-15 → 2026-05-01
  Web URL   : https://www.opensanctions.org/search/?scope=il_mod_crypto&q=…
```

If `targets.simple.csv` is not yet cached, the script prints a tip to download it. For full FtM detail (holder lookup, nested properties), re-run with `--file ftm`.

---

### Step 6 — Interpret and Summarise

Load `references/ftm-schema.md` to decode entity types and property names.

Key fields per entity line:
- `schema` — entity type (`CryptoWallet`, `Person`, `Company`, etc.)
- `caption` — display name
- `properties.topics` — risk tags: `sanction`, `crime`, `pep`, `wanted`, `debarment`
- `properties.publicKey` — wallet address (CryptoWallet only)
- `properties.holder` — entity ID of the wallet's owning person/company
- `datasets` — which OS sources flagged this entity
- `first_seen` / `last_seen` — date range of data currency

For `CryptoWallet` hits, always look up the `holder` entity ID in the same file to name the wallet owner.

**Present results in this format:**

```
## OpenSanctions Results — <dataset_name> (<date>)

### ✅ MATCH — <target>
Schema     : CryptoWallet
Caption    : <caption>
Topics     : sanction, crime.cyber
Datasets   : us_ofac_sdn, il_mod_crypto
publicKey  : <full address>
Holder     : <holder entity name>  [<holder_id>]
Exchange   : <managingExchange if known>
First seen : YYYY-MM-DD  |  Last seen : YYYY-MM-DD

### ❌ NO MATCH — <target>
Not found in `<dataset_name>`. Consider widening to `sanctions` collection.
```

---

## Notes

- **Licensing:** Non-commercial use is free; commercial use requires an OpenSanctions data license
- **Freshness:** The `latest` symlink always points to the most recent export; re-download weekly
- **False positives:** Partial string matches can occur — always verify the full `publicKey` or `name` property
- **Search engine:** FTS5 is the default and needs no extra tools; `rg` (preferred) or `grep` is only used with `--no-fts`
- **Large collections:** `sanctions`, `default`, `crime` are 300–700 MB — always warn before downloading
