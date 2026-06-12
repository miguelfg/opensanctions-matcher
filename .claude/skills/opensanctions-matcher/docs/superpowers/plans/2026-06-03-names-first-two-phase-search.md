# OpenSanctions Names-First Two-Phase Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize `opensanctions-search` to default to `names.txt` (15 KB) instead of `entities.ftm.json` (2+ MB), auto-enrich hits via `targets.simple.csv`, and surface OpenSanctions web URLs for every hit.

**Architecture:** Add four helper functions to `os_search.py` (`os_web_url`, `search_names_txt`, `search_csv`, `format_csv_entity`), extend CLI with `--file` and `--dataset-dir` flags, update `main()` to run a two-phase pipeline (names → CSV enrichment), and update `SKILL.md` to reflect the new default workflow. All existing behaviour is preserved via backwards-compat detection on the `--dataset` flag.

**Tech Stack:** Python 3.10+, `rg`/`grep` (existing), `csv.DictReader` (stdlib), `urllib.parse.quote_plus` (stdlib), `pytest` for tests.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `scripts/os_search.py` | New functions + CLI flags + two-phase `main()` routing |
| Create | `scripts/tests/conftest.py` | Pytest fixtures (tmp dataset dir, fixture file paths) |
| Create | `scripts/tests/fixtures/names.txt` | Sample names for tests |
| Create | `scripts/tests/fixtures/targets.simple.csv` | Sample CSV rows for tests |
| Create | `scripts/tests/test_os_search.py` | Unit + integration tests |
| Modify | `SKILL.md` | Steps 2–5b updated to reflect new default workflow |

---

## Task 1: Test fixtures and conftest

**Files:**
- Create: `scripts/tests/fixtures/names.txt`
- Create: `scripts/tests/fixtures/targets.simple.csv`
- Create: `scripts/tests/conftest.py`

- [ ] **Step 1: Create `names.txt` fixture**

```
# OpenSanctions names fixture — for tests only
TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy
bc1qsanctionedaddress123456789abcdef
0xDeAdBeEfDeAdBeEfDeAdBeEfDeAdBeEf00000001
Alexei Navalny
Hamas Finance Committee
```
Save to: `scripts/tests/fixtures/names.txt`

- [ ] **Step 2: Create `targets.simple.csv` fixture**

```csv
id,caption,schema,name,aliases,identifiers,sanctions,dataset,topics,first_seen,last_seen
Q123,TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy,CryptoWallet,TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy,,TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy,OFAC SDN 2024-01-15,il_mod_crypto,sanction,2024-01-15,2026-05-01
Q124,bc1qsanctionedaddress123456789abcdef,CryptoWallet,bc1qsanctionedaddress123456789abcdef,,bc1qsanctionedaddress123456789abcdef,FBI Lazarus 2023-11-01,us_fbi_lazarus_crypto,crime.cyber,2023-11-01,2026-04-28
Q125,Alexei Navalny,Person,Alexei Navalny,Navalny,,EU FSF 2022-03-01,eu_fsf,sanction,2022-03-01,2026-05-06
```
Save to: `scripts/tests/fixtures/targets.simple.csv`

- [ ] **Step 3: Create `conftest.py`**

```python
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def names_txt():
    return FIXTURES / "names.txt"

@pytest.fixture
def simple_csv():
    return FIXTURES / "targets.simple.csv"

@pytest.fixture
def dataset_dir(tmp_path, names_txt, simple_csv):
    import shutil
    shutil.copy(names_txt, tmp_path / "names.txt")
    shutil.copy(simple_csv, tmp_path / "targets.simple.csv")
    return tmp_path
```
Save to: `scripts/tests/conftest.py`

- [ ] **Step 4: Verify pytest discovers the fixtures**

```bash
cd /path/to/opensanctions-search
python -m pytest scripts/tests/ --collect-only
```
Expected: `no tests ran` (no test file yet) with no collection errors.

- [ ] **Step 5: Commit**

```bash
git add scripts/tests/
git commit -m "test: add opensanctions search test fixtures and conftest"
```

---

## Task 2: `os_web_url()` function

**Files:**
- Modify: `scripts/os_search.py` — add function after imports
- Modify: `scripts/tests/test_os_search.py` — create with first tests

- [ ] **Step 1: Write the failing test**

Create `scripts/tests/test_os_search.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from os_search import os_web_url


def test_os_web_url_basic():
    url = os_web_url("il_mod_crypto", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy")
    assert url == "https://www.opensanctions.org/search/?scope=il_mod_crypto&q=TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"


def test_os_web_url_encodes_spaces():
    url = os_web_url("eu_fsf", "Alexei Navalny")
    assert url == "https://www.opensanctions.org/search/?scope=eu_fsf&q=Alexei+Navalny"


def test_os_web_url_encodes_special_chars():
    url = os_web_url("default", "Müller & Co.")
    assert "M%C3%BCller" in url or "M%c3%bcller" in url
    assert "%26" in url or "&amp;" not in url
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest scripts/tests/test_os_search.py::test_os_web_url_basic -v
```
Expected: `ImportError: cannot import name 'os_web_url'`

- [ ] **Step 3: Add `os_web_url()` to `os_search.py`**

Add after the existing imports (after `from pathlib import Path`):

```python
from urllib.parse import quote_plus
```

Add after the `RISK_TOPICS` dict:

```python
def os_web_url(dataset_name: str, target: str) -> str:
    """Return the OpenSanctions web search URL for a target within a dataset."""
    return f"https://www.opensanctions.org/search/?scope={dataset_name}&q={quote_plus(target)}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest scripts/tests/test_os_search.py -k "web_url" -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: add os_web_url() helper"
```

---

## Task 3: `search_names_txt()` function

**Files:**
- Modify: `scripts/os_search.py` — add function
- Modify: `scripts/tests/test_os_search.py` — add tests

- [ ] **Step 1: Write the failing tests**

Append to `scripts/tests/test_os_search.py`:

```python
from os_search import search_names_txt


def test_search_names_txt_match(names_txt):
    result = search_names_txt(names_txt, ["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"], rg_bin=None)
    assert "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy" in result
    assert result["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"] == ["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"]


def test_search_names_txt_no_match(names_txt):
    result = search_names_txt(names_txt, ["TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"], rg_bin=None)
    assert result["TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"] == []


def test_search_names_txt_skips_comments_and_blanks(tmp_path):
    f = tmp_path / "names.txt"
    f.write_text("# comment line\n\nTARGET_ADDR\n  \n")
    result = search_names_txt(f, ["TARGET_ADDR"], rg_bin=None)
    assert result["TARGET_ADDR"] == ["TARGET_ADDR"]
    result2 = search_names_txt(f, ["comment"], rg_bin=None)
    assert result2["comment"] == []


def test_search_names_txt_case_insensitive(names_txt):
    result = search_names_txt(names_txt, ["tufxua1q"], rg_bin=None)
    assert len(result["tufxua1q"]) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest scripts/tests/test_os_search.py -k "names_txt" -v
```
Expected: `ImportError: cannot import name 'search_names_txt'`

- [ ] **Step 3: Add `search_names_txt()` to `os_search.py`**

Add after `os_web_url()`:

```python
def search_names_txt(path: Path, targets: list[str], rg_bin: str | None) -> dict[str, list[str]]:
    """Search names.txt for each target. Returns {target: [matched_lines]}.

    Strips blank lines and comment lines (starting with #) before matching.
    Matching is case-insensitive substring search.
    """
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = [l for l in raw if l.strip() and not l.strip().startswith("#")]

    results: dict[str, list[str]] = {}
    for target in targets:
        t_lower = target.lower()
        results[target] = [l for l in lines if t_lower in l.lower()]
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest scripts/tests/test_os_search.py -k "names_txt" -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: add search_names_txt() for phase-1 screening"
```

---

## Task 4: `search_csv()` and `format_csv_entity()`

**Files:**
- Modify: `scripts/os_search.py` — add two functions
- Modify: `scripts/tests/test_os_search.py` — add tests

- [ ] **Step 1: Write the failing tests**

Append to `scripts/tests/test_os_search.py`:

```python
from os_search import search_csv, format_csv_entity


def test_search_csv_match(simple_csv):
    result = search_csv(simple_csv, ["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"], rg_bin=None)
    assert "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy" in result
    rows = result["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"]
    assert len(rows) == 1
    assert rows[0]["id"] == "Q123"
    assert rows[0]["schema"] == "CryptoWallet"


def test_search_csv_no_match(simple_csv):
    result = search_csv(simple_csv, ["TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"], rg_bin=None)
    assert result["TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"] == []


def test_search_csv_missing_columns(tmp_path):
    f = tmp_path / "targets.simple.csv"
    f.write_text("id,caption\nQ999,SomeTarget\n")
    result = search_csv(f, ["SomeTarget"], rg_bin=None)
    rows = result["SomeTarget"]
    assert rows[0]["id"] == "Q999"
    assert rows[0].get("schema", "") == ""  # missing column returns empty string


def test_format_csv_entity_basic(simple_csv):
    result = search_csv(simple_csv, ["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"], rg_bin=None)
    row = result["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"][0]
    output = format_csv_entity(row, "il_mod_crypto")
    assert "CryptoWallet" in output
    assert "Q123" in output
    assert "sanction" in output.lower()


def test_format_csv_entity_missing_columns():
    row = {"id": "Q999", "caption": "MinimalRow"}
    output = format_csv_entity(row, "test_dataset")
    assert "Q999" in output
    assert "MinimalRow" in output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest scripts/tests/test_os_search.py -k "csv" -v
```
Expected: `ImportError: cannot import name 'search_csv'`

- [ ] **Step 3: Add `search_csv()` to `os_search.py`**

Add `import csv` to the imports block at top of file. Then add after `search_names_txt()`:

```python
def search_csv(path: Path, targets: list[str], rg_bin: str | None) -> dict[str, list[dict]]:
    """Search targets.simple.csv for each target. Returns {target: [row_dicts]}.

    Uses rg/grep for fast pre-filtering, then parses matching lines with csv.DictReader.
    Missing columns are returned as empty strings (DictReader restval default).
    """
    results: dict[str, list[dict]] = {t: [] for t in targets}
    seen_ids: set[str] = set()

    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        header_line = fh.readline()
        fieldnames = [f.strip() for f in header_line.split(",")]

    for target in targets:
        raw_lines = grep_lines(path, target, rg_bin)
        for line in raw_lines:
            if line.strip().startswith(tuple(fieldnames[:1])):
                continue  # skip header lines that grep may return
            reader = csv.DictReader(
                [header_line.strip() + "\n" + line],
                fieldnames=None,
                restval="",
            )
            for row in reader:
                row_id = row.get("id", "")
                if row_id and row_id in seen_ids:
                    continue
                if row_id:
                    seen_ids.add(row_id)
                results[target].append(dict(row))

    return results
```

- [ ] **Step 4: Add `format_csv_entity()` to `os_search.py`**

Add immediately after `search_csv()`:

```python
def format_csv_entity(row: dict, dataset_name: str) -> str:
    """Render a targets.simple.csv row in the same block style as format_entity()."""
    schema   = row.get("schema", "—")
    caption  = row.get("caption", "—")
    row_id   = row.get("id", "—")
    topics   = row.get("topics", "")
    datasets = row.get("dataset", dataset_name)
    first    = row.get("first_seen", "?")
    last     = row.get("last_seen", "?")

    topic_labels = format_topics([t.strip() for t in topics.split("|") if t.strip()])

    lines = [
        f"  Schema    : {schema}",
        f"  Caption   : {caption}",
        f"  ID        : {row_id}",
        f"  Topics    : {topic_labels or '—'}",
        f"  Datasets  : {datasets}",
    ]

    identifiers = row.get("identifiers", "")
    if identifiers:
        lines.append(f"  Identifiers: {identifiers}")

    name = row.get("name", "")
    aliases = row.get("aliases", "")
    if aliases:
        lines.append(f"  Aliases   : {aliases}")

    sanctions = row.get("sanctions", "")
    if sanctions:
        lines.append(f"  Sanctions : {sanctions}")

    lines.append(f"  Seen      : {first} → {last}")
    return "\n".join(lines)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest scripts/tests/test_os_search.py -k "csv" -v
```
Expected: 5 PASSED

- [ ] **Step 6: Commit**

```bash
git add scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: add search_csv() and format_csv_entity() for phase-2 enrichment"
```

---

## Task 5: CLI flags and two-phase `main()` routing

**Files:**
- Modify: `scripts/os_search.py` — update `main()` and `argparse` block
- Modify: `scripts/tests/test_os_search.py` — add integration tests

- [ ] **Step 1: Write the failing integration tests**

Append to `scripts/tests/test_os_search.py`:

```python
import subprocess


def run_script(args: list[str]) -> subprocess.CompletedProcess:
    script = Path(__file__).parent.parent / "os_search.py"
    return subprocess.run(
        ["python3", str(script)] + args,
        capture_output=True, text=True
    )


def test_main_names_phase1_hit(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"])
    assert "NAMES MATCH" in r.stdout
    assert "opensanctions.org/search" in r.stdout
    assert r.returncode == 0


def test_main_names_phase2_enrichment(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"])
    assert "CryptoWallet" in r.stdout
    assert "Q123" in r.stdout


def test_main_names_no_match(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"])
    assert "NO MATCH" in r.stdout
    assert r.returncode == 2


def test_main_backwards_compat_ftm(dataset_dir):
    # --dataset path/to/entities.ftm.json must still route to FtM path
    ftm = dataset_dir / "entities.ftm.json"
    ftm.write_text('{"id":"x","schema":"CryptoWallet","caption":"x","properties":{"publicKey":["TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"]},"datasets":["test"],"first_seen":"2024-01-01","last_seen":"2026-01-01"}\n')
    r = run_script(["--dataset", str(ftm),
                    "--targets", "TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"])
    assert "CryptoWallet" in r.stdout
    assert r.returncode == 0


def test_main_explicit_file_csv(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--file", "csv",
                    "--targets", "Alexei Navalny"])
    assert "Person" in r.stdout
    assert r.returncode == 0


def test_main_explicit_file_names(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--file", "names",
                    "--targets", "Hamas Finance Committee"])
    assert "NAMES MATCH" in r.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest scripts/tests/test_os_search.py -k "main_" -v
```
Expected: all FAIL with errors about unrecognised arguments `--dataset-dir` / `--file`.

- [ ] **Step 3: Update `argparse` block in `main()`**

Replace the existing `parser.add_argument` block in `main()`:

```python
parser = argparse.ArgumentParser(description="Search OpenSanctions entities")
parser.add_argument("--dataset",
                    help="Path to entities.ftm.json (legacy; implies --file ftm)")
parser.add_argument("--dataset-dir",
                    help="Directory containing names.txt / targets.simple.csv / entities.ftm.json")
parser.add_argument("--file", choices=["names", "csv", "ftm"], default="names",
                    help="Which dataset file to search (default: names)")
parser.add_argument("--targets", nargs="+", default=[],
                    help="Target strings to search for")
parser.add_argument("--targets-file",
                    help="File with one target per line")
parser.add_argument("--schema",
                    help="Filter by FtM schema (only applies to --file ftm)")
parser.add_argument("--no-holder-lookup", action="store_true",
                    help="Skip holder entity lookups (--file ftm only)")
args = parser.parse_args()
```

- [ ] **Step 4: Add backwards-compat detection and path resolution after argparse**

Replace everything from `dataset = Path(args.dataset)...` up to (but not including) the targets loading block:

```python
# Backwards compat: --dataset path/to/entities.ftm.json → force --file ftm
if args.dataset and str(args.dataset).endswith(".ftm.json"):
    args.file = "ftm"
    dataset_path = Path(args.dataset).expanduser()
    dataset_dir = dataset_path.parent
elif args.dataset:
    # --dataset accepted as dataset_dir alias if not a .ftm.json path
    dataset_dir = Path(args.dataset).expanduser()
    dataset_path = dataset_dir / "entities.ftm.json"
elif args.dataset_dir:
    dataset_dir = Path(args.dataset_dir).expanduser()
    dataset_path = dataset_dir / "entities.ftm.json"
else:
    print("ERROR: Provide --dataset or --dataset-dir.", file=sys.stderr)
    sys.exit(1)

file_map = {
    "names": dataset_dir / "names.txt",
    "csv":   dataset_dir / "targets.simple.csv",
    "ftm":   dataset_path,
}
active_file = file_map[args.file]

if not active_file.exists():
    print(f"ERROR: File not found: {active_file}", file=sys.stderr)
    sys.exit(1)
```

- [ ] **Step 5: Replace the search body of `main()` with two-phase routing**

Replace everything from the `rg_bin = find_rg()` line through to `sys.exit(...)` at the end:

```python
rg_bin = find_rg()
search_tool = f"ripgrep ({rg_bin})" if rg_bin else "grep"
dataset_name = dataset_dir.name

print(f"\n{'='*60}")
print(f"OpenSanctions Search")
print(f"  Dataset : {dataset_name}")
print(f"  File    : {active_file.name}")
print(f"  Targets : {len(targets)}")
print(f"  Tool    : {search_tool}")
if args.file == "ftm" and args.schema:
    print(f"  Filter  : schema={args.schema}")
print(f"{'='*60}\n")

total_hits = 0

# ── FtM path (unchanged) ──────────────────────────────────────────────────
if args.file == "ftm":
    for target in targets:
        print(f"── Searching: {target}")
        matches = search_target(target, active_file, args.schema, rg_bin)
        if not matches:
            print(f"  ❌ NO MATCH\n")
            continue
        total_hits += len(matches)
        print(f"  ✅ {len(matches)} match(es) found\n")
        for i, entity in enumerate(matches, 1):
            ctx = entity.pop("_match_context", "")
            ctx_note = f" [matched in: {ctx}]" if ctx == "indirect" else ""
            print(f"  Match {i}{ctx_note}:")
            print(format_entity(entity, target, active_file, rg_bin,
                                lookup_holders=not args.no_holder_lookup))
            print()

# ── CSV path ──────────────────────────────────────────────────────────────
elif args.file == "csv":
    csv_results = search_csv(active_file, targets, rg_bin)
    for target, rows in csv_results.items():
        print(f"── Searching: {target}")
        if not rows:
            print(f"  ❌ NO MATCH\n")
            continue
        total_hits += len(rows)
        print(f"  ✅ {len(rows)} match(es) found\n")
        for i, row in enumerate(rows, 1):
            print(f"  Match {i}:")
            print(format_csv_entity(row, dataset_name))
            print(f"  Web URL   : {os_web_url(dataset_name, target)}")
            print()

# ── Names-first two-phase path (default) ─────────────────────────────────
else:
    names_results = search_names_txt(active_file, targets, rg_bin)
    hit_targets = [t for t, lines in names_results.items() if lines]

    for target, matched_lines in names_results.items():
        print(f"── Searching: {target}")
        if not matched_lines:
            print(f"  ❌ NO MATCH in names.txt")
            print(f"  Tip: rerun with --file ftm for full FtM detail")
            print()
            continue
        total_hits += len(matched_lines)
        print(f"  ✅ NAMES MATCH ({len(matched_lines)} line(s))")
        for line in matched_lines:
            print(f"  Matched : {line}")
        print(f"  Web URL : {os_web_url(dataset_name, target)}")
        print()

    if hit_targets:
        csv_file = dataset_dir / "targets.simple.csv"
        if not csv_file.exists():
            print(f"[info] targets.simple.csv not cached — skipping enrichment")
            print(f"[info] Download it to {csv_file} for property details")
        else:
            print(f"── Phase 2: enriching {len(hit_targets)} hit(s) from targets.simple.csv\n")
            csv_results = search_csv(csv_file, hit_targets, rg_bin)
            for target, rows in csv_results.items():
                if not rows:
                    print(f"  [{target}] not found in CSV (name-only match)\n")
                    continue
                for i, row in enumerate(rows, 1):
                    print(f"  Enrichment for {target} (match {i}):")
                    print(format_csv_entity(row, dataset_name))
                    print()

print(f"{'='*60}")
print(f"Summary: {total_hits} total match(es) across {len(targets)} target(s)")
print(f"{'='*60}\n")

sys.exit(0 if total_hits > 0 else 2)
```

- [ ] **Step 6: Run all tests**

```bash
python -m pytest scripts/tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 7: Smoke test manually**

```bash
python3 scripts/os_search.py \
  --dataset-dir ~/.local/share/opensanctions/il_mod_crypto \
  --targets "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"
```
Expected: Phase 1 names hit (or NO MATCH depending on cache), web URL printed, Phase 2 enrichment if CSV cached.

- [ ] **Step 8: Commit**

```bash
git add scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: two-phase names-first search with CSV enrichment and web URL"
```

---

## Task 6: Update `SKILL.md`

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Update Step 2 — cache check**

Replace the cache-check code block (currently checks `entities.ftm.json`) with:

```bash
ls -lh ~/.local/share/opensanctions/<dataset_name>/<filename> 2>/dev/null \
  && stat -c "%y" ~/.local/share/opensanctions/<dataset_name>/<filename>
```

Where `<filename>` defaults to `names.txt`.

Add table showing the three files and their typical sizes:

```
| File                | Default? | Typical size |
|---------------------|----------|--------------|
| names.txt           | ✅ yes   | ~15 KB       |
| targets.simple.csv  | phase 2  | ~420 KB      |
| entities.ftm.json   | opt-in   | 1–5 MB       |
```

- [ ] **Step 2: Update Step 3 — download confirmation**

Change the example from:
```
Dataset `il_mod_crypto` — Israel Sanctioned Crypto Wallets
Size: 2.5 MB | URL: https://…/entities.ftm.json
```
To:
```
Dataset `il_mod_crypto` — names.txt (Target names text file)
Size: 0.0 MB | URL: https://…/names.txt
```

Update the `curl` snippet to resolve any resource by filename rather than filtering on `'ftm' in mime_type`:

```bash
curl -s "https://data.opensanctions.org/datasets/latest/<dataset>/index.json" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
target = 'names.txt'  # or targets.simple.csv / entities.ftm.json
for r in d.get('resources', []):
    if r.get('path','').endswith(target):
        size_mb = r.get('size', 0) / 1_048_576
        print(f'  File : {r[\"title\"]}')
        print(f'  URL  : {r[\"url\"]}')
        print(f'  Size : {size_mb:.2f} MB')
"
```

- [ ] **Step 3: Update Step 4 — download command**

Change hardcoded `entities.ftm.json` to `<filename>`:

```bash
mkdir -p ~/.local/share/opensanctions/<dataset_name>
wget -q --show-progress \
  "<url_from_index>" \
  -O ~/.local/share/opensanctions/<dataset_name>/<filename>
```

- [ ] **Step 4: Update Step 5 — search command**

Replace:
```bash
python3 <skill_dir>/scripts/os_search.py \
  --dataset ~/.local/share/opensanctions/<dataset_name>/entities.ftm.json \
  --targets "TARGET1" "TARGET2"
```
With:
```bash
python3 <skill_dir>/scripts/os_search.py \
  --dataset-dir ~/.local/share/opensanctions/<dataset_name> \
  --targets "TARGET1" "TARGET2"
```

Remove the `rg -i "WALLET_ADDRESS" … | head -20` pre-screen block (now handled internally by the script).

- [ ] **Step 5: Add Step 5b — two-phase output description**

Add a new section after Step 5:

```markdown
### Step 5b — Two-Phase Output

**Phase 1 — names.txt screen:**
The script prints each matched line and an OpenSanctions web URL for instant
browser lookup:

```
── Searching: TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy
  ✅ NAMES MATCH (1 line)
  Matched : TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy
  Web URL : https://www.opensanctions.org/search/?scope=il_mod_crypto&q=TUFXua1q…
```

**Phase 2 — targets.simple.csv enrichment (auto on hit):**
If `targets.simple.csv` is cached, the script fetches enriched properties:

```
── Phase 2: enriching 1 hit(s) from targets.simple.csv

  Enrichment for TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy (match 1):
  Schema    : CryptoWallet
  Caption   : TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy
  ID        : Q123
  Topics    : 🔴 SANCTION
  Datasets  : il_mod_crypto
  Seen      : 2024-01-15 → 2026-05-01
```

If `targets.simple.csv` is not cached, the script prints a tip to download it.
For full FtM detail (holder lookup, nested properties), re-run with `--file ftm`.
```

- [ ] **Step 6: Verify SKILL.md renders cleanly**

```bash
python3 -c "
with open('SKILL.md') as f:
    text = f.read()
assert 'entities.ftm.json' not in text.replace('entities.ftm.json  |', '').replace('entities.ftm.json (2', '').replace('--file ftm', ''), 'Stale reference found'
print('OK — no stale hardcoded references')
"
```
(Adjust the allowlist as needed for intentional mentions in the file table and opt-in references.)

- [ ] **Step 7: Commit**

```bash
git add SKILL.md
git commit -m "docs: update SKILL.md for names-first two-phase search workflow"
```

---

## Task 7: Final integration check

**Files:** read-only — no changes

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest scripts/tests/ -v --tb=short
```
Expected: all tests PASS, no warnings about missing fixtures.

- [ ] **Step 2: End-to-end smoke test with a real cached dataset**

```bash
python3 scripts/os_search.py \
  --dataset-dir ~/.local/share/opensanctions/ransomwhere \
  --targets "bc1qsomeaddress"
```
Expected: Phase 1 output (MATCH or NO MATCH) and Phase 2 enrichment or tip, no crash.

- [ ] **Step 3: Verify legacy `--dataset` flag still works**

```bash
python3 scripts/os_search.py \
  --dataset ~/.local/share/opensanctions/il_mod_crypto/entities.ftm.json \
  --targets "someaddress"
```
Expected: runs FtM path, header shows `entities.ftm.json`, no error.

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "chore: opensanctions names-first two-phase search — complete"
```
