# FTS5 + Fuzzy Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace grep/substring search in `os_search.py` with SQLite FTS5 as the default engine, and add `--fuzzy [threshold]` for rapidfuzz approximate matching.

**Architecture:** A transparent index layer (`ensure_index`) builds per-file `.fts5.db` caches on first use and rebuilds when the source file is newer. FTS5 with `unicode61` tokenizer replaces all three grep/substring paths. `--fuzzy` runs a rapidfuzz WRatio scan over indexed terms after FTS5, appending approximate-only hits. `--no-fts` bypasses everything, restoring original grep behavior.

**Tech Stack:** Python `sqlite3` (stdlib), `rapidfuzz` (deferred import, only when `--fuzzy` is used), Python 3.10+

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/os_search.py` | Modify | Add 11 new functions, modify 4 existing, add 2 CLI flags |
| `scripts/tests/test_os_search.py` | Modify | Add FTS/fuzzy tests, update 2 integration tests |
| `scripts/tests/conftest.py` | Modify | Add `ftm_json` fixture, update `dataset_dir` |
| `scripts/tests/fixtures/entities.ftm.json` | Create | 3-entity FtM fixture for FtM index tests |

---

### Task 1: `get_index_path`, `index_is_stale`, `fts_query`

**Files:**
- Modify: `scripts/os_search.py`
- Test: `scripts/tests/test_os_search.py`

- [ ] **Step 1: Write the failing tests**

Add to `scripts/tests/test_os_search.py` (after existing imports):

```python
import os
from os_search import get_index_path, index_is_stale, fts_query


def test_get_index_path(tmp_path):
    source = tmp_path / "names.txt"
    source.touch()
    assert get_index_path(source) == tmp_path / "names.txt.fts5.db"


def test_index_is_stale_missing(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("name")
    index = tmp_path / "names.txt.fts5.db"
    assert index_is_stale(source, index) is True


def test_index_is_stale_fresh(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("name")
    index = tmp_path / "names.txt.fts5.db"
    index.touch()
    os.utime(index, (source.stat().st_mtime + 1, source.stat().st_mtime + 1))
    assert index_is_stale(source, index) is False


def test_index_is_stale_source_newer(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("name")
    index = tmp_path / "names.txt.fts5.db"
    index.touch()
    os.utime(source, (index.stat().st_mtime + 1, index.stat().st_mtime + 1))
    assert index_is_stale(source, index) is True


def test_fts_query_multiword():
    assert fts_query("Vladimir Putin") == '"Vladimir Putin"'


def test_fts_query_single_alnum():
    q = fts_query("Gazprom")
    assert q == "Gazprom OR Gazprom*"


def test_fts_query_crypto_address():
    addr = "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"
    assert fts_query(addr) == addr


def test_fts_query_special_chars():
    # Non-alnum single token → quoted phrase (safe fallback)
    q = fts_query("Al-Qaeda")
    assert q.startswith('"') and q.endswith('"')
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /home/miguelfg/workspace/projects/opensanctions-matcher/.claude/skills/opensanctions-matcher
pytest scripts/tests/test_os_search.py -k "test_get_index_path or test_index_is_stale or test_fts_query" -v
```

Expected: `ImportError` — functions not yet defined.

- [ ] **Step 3: Implement the three functions**

Add to `scripts/os_search.py` after the `RISK_TOPICS` dict and before `os_web_url`:

```python
def get_index_path(source: Path) -> Path:
    """Return the FTS5 index path for a source file."""
    return source.parent / (source.name + ".fts5.db")


def index_is_stale(source: Path, index: Path) -> bool:
    """Return True if the index is missing or older than source."""
    if not index.exists():
        return True
    return source.stat().st_mtime > index.stat().st_mtime


def fts_query(target: str) -> str:
    """Build a FTS5 MATCH expression for target.

    - Multi-word  → phrase search "word1 word2"
    - Crypto addr (single token ≥ 20 alnum chars) → exact, no prefix suffix
    - Single alnum word → exact OR prefix* for partial-input tolerance
    - Single word with special chars → quoted phrase (safe fallback)
    """
    stripped = target.strip()
    if " " in stripped:
        return '"' + stripped.replace('"', '""') + '"'
    if len(stripped) >= 20 and stripped.isalnum():
        return stripped
    if stripped.isalnum():
        return f"{stripped} OR {stripped}*"
    return '"' + stripped.replace('"', '""') + '"'
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest scripts/tests/test_os_search.py -k "test_get_index_path or test_index_is_stale or test_fts_query" -v
```

Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: add get_index_path, index_is_stale, fts_query"
```

---

### Task 2: `build_names_index` + `ensure_index`

**Files:**
- Modify: `scripts/os_search.py`
- Test: `scripts/tests/test_os_search.py`

- [ ] **Step 1: Write the failing tests**

```python
import sqlite3
from os_search import build_names_index, ensure_index


def test_build_names_index_creates_db(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("# comment\n\nAlexei Navalny\nGazprom\n")
    index = tmp_path / "names.txt.fts5.db"
    build_names_index(source, index)
    assert index.exists()
    con = sqlite3.connect(index)
    names = [r[0] for r in con.execute("SELECT name FROM names").fetchall()]
    con.close()
    assert set(names) == {"Alexei Navalny", "Gazprom"}


def test_build_names_index_skips_comments(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("# this is a comment\nValidName\n  \n")
    index = tmp_path / "names.txt.fts5.db"
    build_names_index(source, index)
    con = sqlite3.connect(index)
    rows = con.execute("SELECT name FROM names").fetchall()
    con.close()
    assert len(rows) == 1 and rows[0][0] == "ValidName"


def test_ensure_index_builds_on_first_run(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("TestEntry\n")
    result = ensure_index(source, "names")
    assert result == tmp_path / "names.txt.fts5.db"
    assert result.exists()


def test_ensure_index_rebuilds_when_source_newer(tmp_path):
    import time
    source = tmp_path / "names.txt"
    source.write_text("OldEntry\n")
    index = ensure_index(source, "names")
    time.sleep(0.05)
    source.write_text("NewEntry\n")
    os.utime(source, None)
    ensure_index(source, "names")
    con = sqlite3.connect(index)
    rows = con.execute("SELECT name FROM names").fetchall()
    con.close()
    assert rows[0][0] == "NewEntry"


def test_ensure_index_reuses_fresh_index(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Entry\n")
    index = ensure_index(source, "names")
    mtime = index.stat().st_mtime
    ensure_index(source, "names")
    assert index.stat().st_mtime == mtime
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest scripts/tests/test_os_search.py -k "test_build_names or test_ensure_index" -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement**

Add to `scripts/os_search.py` after `fts_query`:

```python
def build_names_index(source: Path, index: Path) -> None:
    """Build FTS5 index for a names.txt file."""
    import sqlite3 as _sq
    raw = source.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = [l for l in raw if l.strip() and not l.strip().startswith("#")]
    con = _sq.connect(index)
    con.execute("CREATE VIRTUAL TABLE names USING fts5(name, tokenize='unicode61')")
    con.executemany("INSERT INTO names(name) VALUES (?)", [(l,) for l in lines])
    con.commit()
    con.close()


def ensure_index(source: Path, file_type: str) -> Path:
    """Return path to a fresh FTS5 index, building or rebuilding as needed."""
    index = get_index_path(source)
    if not index_is_stale(source, index):
        return index
    print(f"[info] Building FTS index for {source.name} (first run or dataset updated)...",
          file=sys.stderr)
    if index.exists():
        index.unlink()
    if file_type == "names":
        build_names_index(source, index)
    elif file_type == "csv":
        build_csv_index(source, index)
    elif file_type == "ftm":
        build_ftm_index(source, index)
    return index
```

Note: `build_csv_index` and `build_ftm_index` are added in later tasks. `ensure_index` will only work for `"names"` until then.

- [ ] **Step 4: Run to verify pass**

```bash
pytest scripts/tests/test_os_search.py -k "test_build_names or test_ensure_index" -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: add build_names_index, ensure_index"
```

---

### Task 3: `search_fts_names` + modify `search_names_txt`

**Files:**
- Modify: `scripts/os_search.py`
- Test: `scripts/tests/test_os_search.py`

- [ ] **Step 1: Write the failing tests**

```python
from os_search import search_fts_names


def test_search_fts_names_hit(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Alexei Navalny\nGazprom\n")
    idx = ensure_index(source, "names")
    assert any("Navalny" in r for r in search_fts_names(idx, "Navalny"))


def test_search_fts_names_miss(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Alexei Navalny\n")
    idx = ensure_index(source, "names")
    assert search_fts_names(idx, "Putin") == []


def test_search_fts_names_multiword(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Alexei Navalny\nNavalny Foundation\n")
    idx = ensure_index(source, "names")
    assert any("Alexei Navalny" in r for r in search_fts_names(idx, "Alexei Navalny"))


def test_search_fts_names_case_insensitive(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Gazprom\n")
    idx = ensure_index(source, "names")
    assert len(search_fts_names(idx, "gazprom")) >= 1


def test_search_names_txt_fts_default(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Alexei Navalny\nGazprom\n")
    result = search_names_txt(source, ["Navalny"], rg_bin=None, use_fts=True)
    assert any("Navalny" in line for line in result["Navalny"])


def test_search_names_txt_no_fts_substring(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Alexei Navalny\nGazprom\n")
    result = search_names_txt(source, ["Nav"], rg_bin=None, use_fts=False)
    assert len(result["Nav"]) == 1  # substring "Nav" inside "Navalny"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest scripts/tests/test_os_search.py -k "test_search_fts_names or test_search_names_txt_fts or test_search_names_txt_no_fts" -v
```

- [ ] **Step 3: Implement**

Add to `scripts/os_search.py` after `ensure_index`:

```python
def search_fts_names(index: Path, target: str) -> list[str]:
    """Search the names.txt FTS5 index. Returns list of matched name strings."""
    import sqlite3 as _sq
    con = _sq.connect(index)
    try:
        rows = con.execute(
            "SELECT name FROM names WHERE names MATCH ? ORDER BY rank",
            (fts_query(target),),
        ).fetchall()
        return [r[0] for r in rows]
    except _sq.OperationalError:
        return []
    finally:
        con.close()
```

Modify the existing `search_names_txt` to add `use_fts` parameter (replace the whole function):

```python
def search_names_txt(path: Path, targets: list[str], rg_bin: str | None,
                     use_fts: bool = True) -> dict[str, list[str]]:
    """Search names.txt for each target. Returns {target: [matched_lines]}.

    use_fts=True (default): FTS5 token-aware search via index.
    use_fts=False: original case-insensitive substring scan.
    """
    if use_fts:
        index = ensure_index(path, "names")
        return {target: search_fts_names(index, target) for target in targets}
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = [l for l in raw if l.strip() and not l.strip().startswith("#")]
    results: dict[str, list[str]] = {}
    for target in targets:
        t_lower = target.lower()
        results[target] = [l for l in lines if t_lower in l.lower()]
    return results
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest scripts/tests/test_os_search.py -k "test_search_fts_names or test_search_names_txt_fts or test_search_names_txt_no_fts" -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: add search_fts_names, FTS-aware search_names_txt"
```

---

### Task 4: `build_csv_index` + `search_fts_csv` + modify `search_csv`

**Files:**
- Modify: `scripts/os_search.py`
- Test: `scripts/tests/test_os_search.py`

- [ ] **Step 1: Write the failing tests**

```python
from os_search import build_csv_index, search_fts_csv


def test_build_csv_index_creates_db(tmp_path):
    source = tmp_path / "targets.simple.csv"
    source.write_text(
        "id,caption,schema,name,aliases,identifiers,sanctions,dataset,topics,first_seen,last_seen\n"
        "Q123,Alexei Navalny,Person,Alexei Navalny,Navalny,,EU FSF,eu_fsf,sanction,2022-03-01,2026-05-06\n"
    )
    index = tmp_path / "targets.simple.csv.fts5.db"
    build_csv_index(source, index)
    assert index.exists()
    con = sqlite3.connect(index)
    rows = con.execute("SELECT id, caption FROM entities").fetchall()
    con.close()
    assert rows[0] == ("Q123", "Alexei Navalny")


def test_search_fts_csv_hit(simple_csv):
    idx = get_index_path(simple_csv)
    build_csv_index(simple_csv, idx)
    results = search_fts_csv(idx, "Navalny")
    assert len(results) == 1
    assert results[0]["id"] == "Q125"
    assert results[0]["schema"] == "Person"


def test_search_fts_csv_miss(simple_csv):
    idx = get_index_path(simple_csv)
    build_csv_index(simple_csv, idx)
    assert search_fts_csv(idx, "NonexistentEntity99999") == []


def test_search_fts_csv_deduplicates(simple_csv):
    idx = get_index_path(simple_csv)
    build_csv_index(simple_csv, idx)
    results = search_fts_csv(idx, "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy")
    assert [r["id"] for r in results].count("Q123") == 1


def test_search_csv_uses_fts_by_default(simple_csv):
    result = search_csv(simple_csv, ["Navalny"], rg_bin=None, use_fts=True)
    assert result["Navalny"][0]["id"] == "Q125"


def test_search_csv_no_fts_fallback(simple_csv):
    result = search_csv(simple_csv, ["Navalny"], rg_bin=None, use_fts=False)
    assert result["Navalny"][0]["id"] == "Q125"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest scripts/tests/test_os_search.py -k "test_build_csv or test_search_fts_csv or test_search_csv_uses_fts or test_search_csv_no_fts" -v
```

- [ ] **Step 3: Implement**

Add to `scripts/os_search.py` after `search_fts_names`:

```python
def build_csv_index(source: Path, index: Path) -> None:
    """Build FTS5 index for a targets.simple.csv file."""
    import sqlite3 as _sq
    con = _sq.connect(index)
    con.execute("""
        CREATE VIRTUAL TABLE entities USING fts5(
            id          UNINDEXED,
            caption,
            aliases,
            identifiers,
            raw_row     UNINDEXED,
            tokenize    = 'unicode61'
        )
    """)
    with open(source, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        batch = []
        for row in reader:
            batch.append((
                row.get("id", ""),
                row.get("caption", ""),
                row.get("aliases", ""),
                row.get("identifiers", ""),
                json.dumps(dict(row)),
            ))
            if len(batch) >= 1000:
                con.executemany("INSERT INTO entities VALUES (?,?,?,?,?)", batch)
                batch = []
    if batch:
        con.executemany("INSERT INTO entities VALUES (?,?,?,?,?)", batch)
    con.commit()
    con.close()


def search_fts_csv(index: Path, target: str) -> list[dict]:
    """Search the CSV FTS5 index. Returns list of row dicts."""
    import sqlite3 as _sq
    con = _sq.connect(index)
    try:
        rows = con.execute(
            "SELECT id, raw_row FROM entities WHERE entities MATCH ? ORDER BY rank",
            (fts_query(target),),
        ).fetchall()
        results, seen: list[dict], set[str] = [], set()
        for entity_id, raw in rows:
            if entity_id in seen:
                continue
            seen.add(entity_id)
            try:
                results.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return results
    except _sq.OperationalError:
        return []
    finally:
        con.close()
```

Replace the existing `search_csv` function:

```python
def search_csv(path: Path, targets: list[str], rg_bin: str | None,
               use_fts: bool = True) -> dict[str, list[dict]]:
    """Search targets.simple.csv for each target. Returns {target: [row_dicts]}.

    use_fts=True (default): FTS5 index.
    use_fts=False: original grep/csv path.
    """
    if use_fts:
        index = ensure_index(path, "csv")
        return {target: search_fts_csv(index, target) for target in targets}

    results: dict[str, list[dict]] = {t: [] for t in targets}
    seen_ids: set[str] = set()
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        header_line = fh.readline().strip()
    fieldnames = [f.strip() for f in header_line.split(",")]
    for target in targets:
        raw_lines = grep_lines(path, target, rg_bin)
        for line in raw_lines:
            if line.strip().startswith(tuple(fieldnames[:1])):
                continue
            csv_text = header_line + "\n" + line
            reader = csv.DictReader(io.StringIO(csv_text), fieldnames=None, restval="")
            for row in reader:
                row_id = row.get("id", "")
                if row_id and row_id in seen_ids:
                    continue
                if row_id:
                    seen_ids.add(row_id)
                results[target].append(dict(row))
    return results
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest scripts/tests/test_os_search.py -v
```

Expected: all tests PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: add build_csv_index, search_fts_csv, FTS-aware search_csv"
```

---

### Task 5: FtM fixture + `build_ftm_index` + `search_fts_ftm` + modify `search_target`

**Files:**
- Create: `scripts/tests/fixtures/entities.ftm.json`
- Modify: `scripts/tests/conftest.py`
- Modify: `scripts/os_search.py`
- Test: `scripts/tests/test_os_search.py`

- [ ] **Step 1: Create `scripts/tests/fixtures/entities.ftm.json`**

Exact content (one JSON object per line, no trailing newline after last):

```
{"id":"Q200","schema":"CryptoWallet","caption":"0xDeAdBeEfDeAdBeEfDeAdBeEfDeAdBeEf00000001","properties":{"publicKey":["0xDeAdBeEfDeAdBeEfDeAdBeEfDeAdBeEf00000001"],"holder":["Q201"],"topics":["sanction"]},"datasets":["us_ofac_sdn"],"first_seen":"2024-01-01","last_seen":"2026-01-01"}
{"id":"Q201","schema":"Person","caption":"Alexei Navalny","properties":{"name":["Alexei Navalny"],"alias":["Navalny","А. Навальный"],"topics":["sanction"]},"datasets":["eu_fsf"],"first_seen":"2022-03-01","last_seen":"2026-05-06"}
{"id":"Q202","schema":"Company","caption":"Hamas Finance Committee","properties":{"name":["Hamas Finance Committee"],"alias":["HFC"],"topics":["sanction","crime.terror"]},"datasets":["us_ofac_sdn"],"first_seen":"2021-01-01","last_seen":"2026-05-01"}
```

- [ ] **Step 2: Update `scripts/tests/conftest.py`**

Replace entire file content:

```python
import shutil
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def names_txt() -> Path:
    return FIXTURES / "names.txt"


@pytest.fixture
def simple_csv() -> Path:
    return FIXTURES / "targets.simple.csv"


@pytest.fixture
def ftm_json() -> Path:
    return FIXTURES / "entities.ftm.json"


@pytest.fixture
def dataset_dir(tmp_path: Path, names_txt: Path, simple_csv: Path, ftm_json: Path) -> Path:
    """Copy all fixture files into a temp dir."""
    shutil.copy(names_txt, tmp_path / "names.txt")
    shutil.copy(simple_csv, tmp_path / "targets.simple.csv")
    shutil.copy(ftm_json, tmp_path / "entities.ftm.json")
    return tmp_path
```

- [ ] **Step 3: Write the failing tests**

Add to `scripts/tests/test_os_search.py` (add `import shutil` near top imports):

```python
import shutil
from os_search import build_ftm_index, search_fts_ftm


def test_build_ftm_index_creates_db(ftm_json, tmp_path):
    index = tmp_path / "entities.ftm.json.fts5.db"
    build_ftm_index(ftm_json, index)
    assert index.exists()
    con = sqlite3.connect(index)
    ids = [r[0] for r in con.execute("SELECT id FROM entities").fetchall()]
    con.close()
    assert set(ids) == {"Q200", "Q201", "Q202"}


def test_build_ftm_index_indexes_aliases(ftm_json, tmp_path):
    index = tmp_path / "entities.ftm.json.fts5.db"
    build_ftm_index(ftm_json, index)
    con = sqlite3.connect(index)
    rows = con.execute(
        "SELECT id FROM entities WHERE entities MATCH 'HFC'"
    ).fetchall()
    con.close()
    assert ("Q202",) in rows


def test_search_fts_ftm_hit(ftm_json, tmp_path):
    index = tmp_path / "entities.ftm.json.fts5.db"
    build_ftm_index(ftm_json, index)
    results = search_fts_ftm(index, "Navalny")
    assert len(results) == 1 and results[0]["id"] == "Q201"


def test_search_fts_ftm_miss(ftm_json, tmp_path):
    index = tmp_path / "entities.ftm.json.fts5.db"
    build_ftm_index(ftm_json, index)
    assert search_fts_ftm(index, "NonexistentXYZ99999") == []


def test_search_target_uses_fts(ftm_json, tmp_path):
    shutil.copy(ftm_json, tmp_path / "entities.ftm.json")
    dataset = tmp_path / "entities.ftm.json"
    results = search_target("Navalny", dataset, schema_filter=None, rg_bin=None, use_fts=True)
    assert len(results) == 1 and results[0]["id"] == "Q201"


def test_search_target_schema_filter_with_fts(ftm_json, tmp_path):
    shutil.copy(ftm_json, tmp_path / "entities.ftm.json")
    dataset = tmp_path / "entities.ftm.json"
    assert search_target("Navalny", dataset, "Company", rg_bin=None, use_fts=True) == []
    assert search_target("Navalny", dataset, "Person", rg_bin=None, use_fts=True)[0]["id"] == "Q201"
```

- [ ] **Step 4: Run to verify failure**

```bash
pytest scripts/tests/test_os_search.py -k "test_build_ftm or test_search_fts_ftm or test_search_target" -v
```

- [ ] **Step 5: Implement**

Add to `scripts/os_search.py` after `search_fts_csv`:

```python
def build_ftm_index(source: Path, index: Path) -> None:
    """Build FTS5 index for an entities.ftm.json file."""
    import sqlite3 as _sq
    con = _sq.connect(index)
    con.execute("""
        CREATE VIRTUAL TABLE entities USING fts5(
            id        UNINDEXED,
            caption,
            names,
            aliases,
            raw_json  UNINDEXED,
            tokenize  = 'unicode61'
        )
    """)
    batch, row_count = [], 0
    with open(source, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            entity = parse_entity(line)
            if entity is None:
                continue
            props = entity.get("properties", {})
            batch.append((
                entity.get("id", ""),
                entity.get("caption", ""),
                " ".join(props.get("name", [])),
                " ".join(props.get("alias", [])),
                line.strip(),
            ))
            row_count += 1
            if len(batch) >= 1000:
                con.executemany("INSERT INTO entities VALUES (?,?,?,?,?)", batch)
                batch = []
            if row_count % 100_000 == 0:
                print(f"[info] Indexed {row_count:,} entities...", file=sys.stderr)
    if batch:
        con.executemany("INSERT INTO entities VALUES (?,?,?,?,?)", batch)
    con.commit()
    con.close()


def search_fts_ftm(index: Path, target: str) -> list[dict]:
    """Search the FtM JSON FTS5 index. Returns list of parsed entity dicts."""
    import sqlite3 as _sq
    con = _sq.connect(index)
    try:
        rows = con.execute(
            "SELECT id, raw_json FROM entities WHERE entities MATCH ? ORDER BY rank",
            (fts_query(target),),
        ).fetchall()
        results, seen = [], set()
        for entity_id, raw_json in rows:
            if entity_id in seen:
                continue
            seen.add(entity_id)
            entity = parse_entity(raw_json)
            if entity:
                results.append(entity)
        return results
    except _sq.OperationalError:
        return []
    finally:
        con.close()
```

Replace the existing `search_target` function:

```python
def search_target(target: str, dataset: Path, schema_filter: str | None,
                  rg_bin: str | None, use_fts: bool = True) -> list[dict]:
    """Find all entities matching target string in the dataset."""
    if use_fts:
        index = ensure_index(dataset, "ftm")
        entities = search_fts_ftm(index, target)
        if schema_filter:
            entities = [e for e in entities if e.get("schema") == schema_filter]
        for entity in entities:
            if entity.get("schema") == "CryptoWallet":
                public_keys = [k.lower() for k in prop(entity, "publicKey")]
                entity["_match_context"] = (
                    "publicKey" if any(target.lower() in k for k in public_keys) else "indirect"
                )
            else:
                entity["_match_context"] = "name_or_text"
        return entities

    raw_lines = grep_lines(dataset, target, rg_bin)
    entities, seen_ids = [], set()
    for line in raw_lines:
        entity = parse_entity(line)
        if entity is None:
            continue
        entity_id = entity.get("id")
        if entity_id in seen_ids:
            continue
        seen_ids.add(entity_id)
        if schema_filter and entity.get("schema") != schema_filter:
            continue
        if entity.get("schema") == "CryptoWallet":
            public_keys = [k.lower() for k in prop(entity, "publicKey")]
            entity["_match_context"] = (
                "publicKey" if any(target.lower() in k for k in public_keys) else "indirect"
            )
        else:
            entity["_match_context"] = "name_or_text"
        entities.append(entity)
    return entities
```

- [ ] **Step 6: Run full suite**

```bash
pytest scripts/tests/test_os_search.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/tests/fixtures/entities.ftm.json scripts/tests/conftest.py \
        scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: add FtM fixture, build_ftm_index, search_fts_ftm, FTS-aware search_target"
```

---

### Task 6: `--no-fts` flag + output label change

**Files:**
- Modify: `scripts/os_search.py`
- Modify: `scripts/tests/test_os_search.py`

- [ ] **Step 1: Write failing tests and update two existing tests**

Update these two existing tests (change `"NAMES MATCH"` → `"FTS MATCH"`):

```python
def test_main_names_phase1_hit(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"])
    assert "FTS MATCH" in r.stdout   # was "NAMES MATCH"
    assert "opensanctions.org/search" in r.stdout
    assert r.returncode == 0


def test_main_explicit_file_names(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--file", "names",
                    "--targets", "Hamas Finance Committee"])
    assert "FTS MATCH" in r.stdout   # was "NAMES MATCH"
```

Add new tests:

```python
def test_main_no_fts_uses_names_match_label(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy",
                    "--no-fts"])
    assert "NAMES MATCH" in r.stdout
    assert r.returncode == 0


def test_main_no_fts_still_returns_results(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy",
                    "--no-fts"])
    assert r.returncode == 0
    assert "CryptoWallet" in r.stdout
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest scripts/tests/test_os_search.py -k "test_main_names_phase1_hit or test_main_explicit_file_names or test_main_no_fts" -v
```

- [ ] **Step 3: Add `--no-fts` to `main` and thread `use_fts` through all calls**

In `main()` in `scripts/os_search.py`:

After `--no-holder-lookup`, add:
```python
parser.add_argument("--no-fts", action="store_true",
                    help="Disable FTS5 index; use original grep/substring search")
```

After `rg_bin = find_rg()`, add:
```python
use_fts = not args.no_fts
```

Make these four replacements in `main`:

1. Names path:
```python
# before:
names_results = search_names_txt(active_file, targets, rg_bin)
# after:
names_results = search_names_txt(active_file, targets, rg_bin, use_fts=use_fts)
```

2. Phase 2 CSV inside names path:
```python
# before:
csv_results = search_csv(csv_file, hit_targets, rg_bin)
# after:
csv_results = search_csv(csv_file, hit_targets, rg_bin, use_fts=use_fts)
```

3. Explicit `--file csv` path:
```python
# before:
csv_results = search_csv(active_file, targets, rg_bin)
# after:
csv_results = search_csv(active_file, targets, rg_bin, use_fts=use_fts)
```

4. FtM path:
```python
# before:
matches = search_target(target, active_file, args.schema, rg_bin)
# after:
matches = search_target(target, active_file, args.schema, rg_bin, use_fts=use_fts)
```

Change the NAMES MATCH label. Find:
```python
print(f"  ✅ NAMES MATCH ({len(matched_lines)} line(s))")
```
Replace with:
```python
match_label = "NAMES MATCH" if args.no_fts else "FTS MATCH"
print(f"  ✅ {match_label} ({len(matched_lines)} line(s))")
```

- [ ] **Step 4: Run full suite**

```bash
pytest scripts/tests/test_os_search.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: add --no-fts flag, default label FTS MATCH"
```

---

### Task 7: `search_fuzzy`

**Files:**
- Modify: `scripts/os_search.py`
- Test: `scripts/tests/test_os_search.py`

- [ ] **Step 1: Write failing tests**

```python
from os_search import search_fuzzy


def test_search_fuzzy_names_finds_approximate(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Vladimir Putin\nVladimyr Pootin\nGazprom\n")
    idx = ensure_index(source, "names")
    fts_hits = set(search_fts_names(idx, "Vladimir Putin"))
    results = search_fuzzy(idx, "Vladimir Putin", threshold=70,
                           file_type="names", existing_ids=fts_hits)
    assert any(r["_fuzzy_match"] == "Vladimyr Pootin" for r in results)


def test_search_fuzzy_names_threshold(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Vladimir Putin\nXyzzy Completely Different\n")
    idx = ensure_index(source, "names")
    results = search_fuzzy(idx, "Vladimir Putin", threshold=95,
                           file_type="names", existing_ids=set())
    assert not any(r["_fuzzy_match"] == "Xyzzy Completely Different" for r in results)


def test_search_fuzzy_names_deduplicates(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Vladimir Putin\n")
    idx = ensure_index(source, "names")
    results = search_fuzzy(idx, "Vladimir Putin", threshold=80,
                           file_type="names", existing_ids={"Vladimir Putin"})
    assert not any(r["_fuzzy_match"] == "Vladimir Putin" for r in results)


def test_search_fuzzy_csv_finds_approximate(simple_csv):
    idx = ensure_index(simple_csv, "csv")
    results = search_fuzzy(idx, "Aleksei Navalnyy", threshold=70,
                           file_type="csv", existing_ids=set())
    assert any("Navalny" in r.get("caption", "") for r in results)


def test_search_fuzzy_missing_rapidfuzz(tmp_path, monkeypatch, capsys):
    import builtins
    real = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "rapidfuzz":
            raise ImportError("No module named 'rapidfuzz'")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    source = tmp_path / "names.txt"
    source.write_text("Test\n")
    idx = ensure_index(source, "names")
    result = search_fuzzy(idx, "Test", 80, "names", existing_ids=set())
    assert result == []
    assert "pip install rapidfuzz" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest scripts/tests/test_os_search.py -k "test_search_fuzzy" -v
```

- [ ] **Step 3: Implement**

Add to `scripts/os_search.py` after `search_fts_ftm`:

```python
def search_fuzzy(
    index: Path,
    target: str,
    threshold: int,
    file_type: str,
    existing_ids: set[str] | None = None,
) -> list[dict]:
    """Rapidfuzz WRatio scan over index terms. Returns hits not in existing_ids.

    file_type='names'    → existing_ids contains matched name strings.
    file_type='csv'/'ftm' → existing_ids contains entity ID strings.
    Each result has '_fuzzy_score'; names results also have '_fuzzy_match'.
    """
    try:
        from rapidfuzz import process as rp, fuzz
    except ImportError:
        print("[error] --fuzzy requires rapidfuzz: pip install rapidfuzz", file=sys.stderr)
        return []

    import sqlite3 as _sq

    existing_ids = existing_ids or set()
    con = _sq.connect(index)
    try:
        if file_type == "names":
            choices = {r[0]: r[0] for r in con.execute("SELECT name FROM names").fetchall()}
            return [
                {"_fuzzy_match": name, "_fuzzy_score": int(score)}
                for name, score, _ in rp.extract(target, choices, scorer=fuzz.WRatio,
                                                  score_cutoff=threshold)
                if name not in existing_ids
            ]

        elif file_type == "csv":
            rows = con.execute("SELECT id, caption, raw_row FROM entities").fetchall()
            choices = {r[0]: r[1] for r in rows}
            raw_by_id = {r[0]: r[2] for r in rows}
            results = []
            for caption, score, entity_id in rp.extract(target, choices, scorer=fuzz.WRatio,
                                                         score_cutoff=threshold):
                if entity_id in existing_ids:
                    continue
                try:
                    row = json.loads(raw_by_id[entity_id])
                    row["_fuzzy_score"] = int(score)
                    results.append(row)
                except (json.JSONDecodeError, KeyError):
                    continue
            return results

        elif file_type == "ftm":
            rows = con.execute("SELECT id, caption, raw_json FROM entities").fetchall()
            choices = {r[0]: r[1] for r in rows}
            raw_by_id = {r[0]: r[2] for r in rows}
            results = []
            for caption, score, entity_id in rp.extract(target, choices, scorer=fuzz.WRatio,
                                                         score_cutoff=threshold):
                if entity_id in existing_ids:
                    continue
                entity = parse_entity(raw_by_id.get(entity_id, ""))
                if entity:
                    entity["_fuzzy_score"] = int(score)
                    results.append(entity)
            return results

    finally:
        con.close()

    return []
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest scripts/tests/test_os_search.py -k "test_search_fuzzy" -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: add search_fuzzy with rapidfuzz WRatio"
```

---

### Task 8: `--fuzzy` CLI flag + wire into all paths + performance warning

**Files:**
- Modify: `scripts/os_search.py`
- Test: `scripts/tests/test_os_search.py`

- [ ] **Step 1: Write failing integration tests**

```python
def test_main_fuzzy_flag_no_threshold(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy",
                    "--fuzzy"])
    assert r.returncode == 0


def test_main_fuzzy_custom_threshold(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "Aleksei Navalnyy",
                    "--fuzzy", "65"])
    # Approximate match for "Alexei Navalny" fixture entry; may or may not hit
    assert r.returncode in (0, 2)


def test_main_fuzzy_shows_fuzzy_label(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "Aleksei Navalniy",
                    "--fuzzy", "65"])
    if r.returncode == 0:
        assert "FUZZY" in r.stdout


def test_main_no_fts_with_fuzzy_still_works(dataset_dir):
    """--no-fts disables fuzzy silently; search still returns results."""
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy",
                    "--no-fts", "--fuzzy"])
    assert r.returncode == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest scripts/tests/test_os_search.py -k "test_main_fuzzy" -v
```

Expected: argparse error — `--fuzzy` unknown.

- [ ] **Step 3: Add `_check_large_dataset` helper before `main`**

Add to `scripts/os_search.py` just before the `main` function:

```python
def _check_large_dataset(index: Path, table: str) -> None:
    """Warn if the dataset has more than 500,000 entries (fuzzy scan will be slow)."""
    import sqlite3 as _sq
    try:
        con = _sq.connect(index)
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        con.close()
        if count > 500_000:
            print(
                f"[warn] Fuzzy scan on large dataset ({count:,} entries) — this may take a moment",
                file=sys.stderr,
            )
    except Exception:
        pass
```

- [ ] **Step 4: Add `--fuzzy` arg to `main` and set `fuzzy_threshold`**

In `main()`, after `--no-fts`:

```python
parser.add_argument(
    "--fuzzy", nargs="?", const=80, type=int, metavar="THRESHOLD",
    help="Enable fuzzy matching via rapidfuzz WRatio (default threshold: 80)",
)
```

After `use_fts = not args.no_fts`, add:

```python
fuzzy_threshold: int | None = None if args.no_fts else args.fuzzy
```

- [ ] **Step 5: Wire fuzzy into the names-first path**

Replace the names-first loop in `main` (the `else:` block) with:

```python
else:
    names_results = search_names_txt(active_file, targets, rg_bin, use_fts=use_fts)
    if fuzzy_threshold is not None:
        idx = get_index_path(active_file)
        if idx.exists():
            _check_large_dataset(idx, "names")

    hit_targets = []
    for target, matched_lines in names_results.items():
        print(f"── Searching: {target}")
        fts_hit_set = set(matched_lines)

        fuzzy_name_hits: list[dict] = []
        if fuzzy_threshold is not None:
            idx = get_index_path(active_file)
            if idx.exists():
                fuzzy_name_hits = search_fuzzy(idx, target, fuzzy_threshold,
                                               "names", existing_ids=fts_hit_set)

        if not matched_lines and not fuzzy_name_hits:
            print(f"  ❌ NO MATCH in names.txt")
            print(f"  Tip: rerun with --file ftm for full FtM detail")
            print()
            continue

        total_hits += len(matched_lines) + len(fuzzy_name_hits)

        if matched_lines:
            match_label = "NAMES MATCH" if args.no_fts else "FTS MATCH"
            print(f"  ✅ {match_label} ({len(matched_lines)} line(s))")
            for line in matched_lines:
                print(f"  Matched : {line}")
            hit_targets.append(target)

        for hit in fuzzy_name_hits:
            print(f"  ⚠️  FUZZY MATCH (score: {hit['_fuzzy_score']}) — {hit['_fuzzy_match']}")

        print(f"  Web URL : {os_web_url(dataset_name, target)}")
        print()

    if hit_targets:
        csv_file = dataset_dir / "targets.simple.csv"
        if not csv_file.exists():
            print(f"[info] targets.simple.csv not cached — skipping enrichment")
            print(f"[info] Download it to {csv_file} for property details")
        else:
            print(f"── Phase 2: enriching {len(hit_targets)} hit(s) from targets.simple.csv\n")
            csv_results = search_csv(csv_file, hit_targets, rg_bin, use_fts=use_fts)
            for target, rows in csv_results.items():
                if not rows:
                    print(f"  [{target}] not found in CSV (name-only match)\n")
                    continue
                for i, row in enumerate(rows, 1):
                    print(f"  Enrichment for {target} (match {i}):")
                    print(format_csv_entity(row, dataset_name))
                    print(f"  Web URL   : {os_web_url(dataset_name, target)}")
                    print()
```

- [ ] **Step 6: Wire fuzzy into the explicit `--file csv` path**

In the `elif args.file == "csv":` block, replace the per-target output loop with:

```python
elif args.file == "csv":
    csv_results = search_csv(active_file, targets, rg_bin, use_fts=use_fts)
    for target, rows in csv_results.items():
        print(f"── Searching: {target}")
        fts_ids = {r.get("id", "") for r in rows}

        fuzzy_extras: list[dict] = []
        if fuzzy_threshold is not None:
            idx = get_index_path(active_file)
            if idx.exists():
                _check_large_dataset(idx, "entities")
                fuzzy_extras = search_fuzzy(idx, target, fuzzy_threshold,
                                            "csv", existing_ids=fts_ids)

        all_rows = rows + fuzzy_extras
        if not all_rows:
            print(f"  ❌ NO MATCH\n")
            continue
        total_hits += len(all_rows)
        print(f"  ✅ {len(all_rows)} match(es) found\n")
        for i, row in enumerate(all_rows, 1):
            score = row.pop("_fuzzy_score", None)
            label = f"  ⚠️  Fuzzy Match {i} (score: {score}):" if score else f"  Match {i}:"
            print(label)
            print(format_csv_entity(row, dataset_name))
            print(f"  Web URL   : {os_web_url(dataset_name, target)}")
            print()
```

- [ ] **Step 7: Wire fuzzy into the `--file ftm` path**

In the `if args.file == "ftm":` block, replace the per-target output loop with:

```python
if args.file == "ftm":
    for target in targets:
        print(f"── Searching: {target}")
        matches = search_target(target, active_file, args.schema, rg_bin, use_fts=use_fts)
        fts_ids = {e.get("id", "") for e in matches}

        fuzzy_extras: list[dict] = []
        if fuzzy_threshold is not None:
            idx = get_index_path(active_file)
            if idx.exists():
                _check_large_dataset(idx, "entities")
                fuzzy_extras = search_fuzzy(idx, target, fuzzy_threshold,
                                            "ftm", existing_ids=fts_ids)

        all_matches = matches + fuzzy_extras
        if not all_matches:
            print(f"  ❌ NO MATCH\n")
            continue
        total_hits += len(all_matches)
        print(f"  ✅ {len(all_matches)} match(es) found\n")
        for i, entity in enumerate(all_matches, 1):
            ctx = entity.pop("_match_context", "")
            score = entity.pop("_fuzzy_score", None)
            ctx_note = f" [matched in: {ctx}]" if ctx == "indirect" else ""
            label = (f"  ⚠️  Fuzzy Match {i} (score: {score}){ctx_note}:"
                     if score else f"  Match {i}{ctx_note}:")
            print(label)
            print(format_entity(entity, target, active_file, rg_bin,
                                lookup_holders=not args.no_holder_lookup))
            print()
```

- [ ] **Step 8: Run full test suite**

```bash
pytest scripts/tests/test_os_search.py -v
```

Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add scripts/os_search.py scripts/tests/test_os_search.py
git commit -m "feat: add --fuzzy flag, wire into all search paths, add performance warning"
```
