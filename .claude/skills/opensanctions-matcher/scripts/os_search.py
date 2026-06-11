#!/usr/bin/env python3
"""
OpenSanctions FtM entity search.

Searches one or more targets against a local entities.ftm.json file.
Uses ripgrep (rg) for fast pre-filtering, then parses matching JSON lines
for structured FtM output.

Usage:
    python3 os_search.py --dataset PATH --targets TARGET [TARGET ...]
    python3 os_search.py --dataset PATH --targets-file targets.txt
    python3 os_search.py --dataset PATH --targets TARGET --schema CryptoWallet

Examples:
    python3 os_search.py \\
        --dataset ~/.local/share/opensanctions/il_mod_crypto/entities.ftm.json \\
        --targets "0xABC123" "bc1qabc"

    python3 os_search.py \\
        --dataset ~/.local/share/opensanctions/us_ofac_sdn/entities.ftm.json \\
        --targets "Putin" "Gazprom" --schema Person
"""

import argparse
import csv
import io
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote_plus


RISK_TOPICS = {
    "sanction": "🔴 SANCTION",
    "sanction.linked": "🟠 SANCTION-LINKED",
    "sanction.counter": "🟡 COUNTER-SANCTION",
    "debarment": "🔴 DEBARMENT",
    "debarment.linked": "🟠 DEBARMENT-LINKED",
    "crime": "🔴 CRIME",
    "crime.fraud": "🔴 FRAUD",
    "crime.cyber": "🔴 CYBERCRIME",
    "crime.terror": "🔴 TERRORISM",
    "crime.traffick": "🔴 TRAFFICKING",
    "crime.fin": "🔴 FINANCIAL CRIME",
    "pep": "🟡 PEP",
    "pep.linked": "🟡 PEP-LINKED",
    "wanted": "🔴 WANTED",
    "asset": "🟠 SANCTIONED ASSET",
    "reg.action": "🟠 REG ACTION",
}


def get_index_path(source: Path) -> Path:
    """Return the FTS5 index path for a source file."""
    return source.parent / (source.name + ".fts5.db")


def index_is_stale(source: Path, index: Path) -> bool:
    """Return True if the index is missing or older than source."""
    if not index.exists():
        return True
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    return source.stat().st_mtime > index.stat().st_mtime


def fts_query(target: str) -> str:
    """Build a FTS5 MATCH expression for target.

    Multi-word → phrase search "word1 word2"
    Crypto addr (single token >= 20 alnum chars) → exact, no prefix suffix
    Single alnum word → exact OR prefix* for partial-input tolerance
    Single word with special chars → quoted phrase (safe fallback)
    """
    stripped = target.strip()
    if not stripped:
        raise ValueError("fts_query requires a non-empty target string")
    if " " in stripped:
        return '"' + stripped.replace('"', '""') + '"'
    if len(stripped) >= 20 and stripped.isalnum():
        return stripped
    if stripped.isalnum():
        return f"{stripped} OR {stripped}*"
    return '"' + stripped.replace('"', '""') + '"'


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
    except _sq.DatabaseError:
        return []
    finally:
        con.close()


def build_csv_index(source: Path, index: Path) -> None:
    """Build FTS5 index for a targets.simple.csv file."""
    import sqlite3 as _sq
    con = _sq.connect(index)
    con.execute("DROP TABLE IF EXISTS entities")
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
        results: list[dict] = []
        seen: set[str] = set()
        for entity_id, raw in rows:
            if entity_id in seen:
                continue
            seen.add(entity_id)
            try:
                results.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return results
    except _sq.DatabaseError:
        return []
    finally:
        con.close()


def build_ftm_index(source: Path, index: Path) -> None:
    """Build FTS5 index for an entities.ftm.json file."""
    import sqlite3 as _sq
    con = _sq.connect(index)
    con.execute("DROP TABLE IF EXISTS entities")
    con.execute("""
        CREATE VIRTUAL TABLE entities USING fts5(
            id          UNINDEXED,
            caption,
            names,
            aliases,
            identifiers,
            raw_json    UNINDEXED,
            tokenize    = 'unicode61'
        )
    """)
    batch, row_count = [], 0
    with open(source, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            entity = parse_entity(line)
            if entity is None:
                continue
            props = entity.get("properties", {})
            # Index common identifier properties so wallet addresses and document
            # numbers are searchable. Extend this list as the FtM schema evolves.
            identifiers = " ".join(
                v
                for key in ("publicKey", "ibanNumber", "registrationNumber",
                            "taxNumber", "passportNumber", "idNumber")
                for v in props.get(key, [])
            )
            batch.append((
                entity.get("id", ""),
                entity.get("caption", ""),
                " ".join(props.get("name", [])),
                " ".join(props.get("alias", [])),
                identifiers,
                line.strip(),
            ))
            row_count += 1
            if len(batch) >= 1000:
                con.executemany("INSERT INTO entities VALUES (?,?,?,?,?,?)", batch)
                batch = []
            if row_count % 100_000 == 0:
                print(f"[info] Indexed {row_count:,} entities...", file=sys.stderr)
    if batch:
        con.executemany("INSERT INTO entities VALUES (?,?,?,?,?,?)", batch)
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
        results: list[dict] = []
        seen: set[str] = set()
        for entity_id, raw_json in rows:
            if entity_id in seen:
                continue
            seen.add(entity_id)
            entity = parse_entity(raw_json)
            if entity:
                results.append(entity)
        return results
    except _sq.DatabaseError:
        return []
    finally:
        con.close()


def search_fuzzy(
    index: Path,
    target: str,
    threshold: int,
    file_type: str,
    existing_ids: set[str] | None = None,
) -> list[dict]:
    """Rapidfuzz WRatio scan over index terms. Returns hits not in existing_ids.

    file_type='names'     → existing_ids contains matched name strings.
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
                for name, score, _ in rp.extract(
                    target, choices, scorer=fuzz.WRatio, score_cutoff=threshold
                )
                if name not in existing_ids
            ]

        elif file_type == "csv":
            rows = con.execute("SELECT id, caption, raw_row FROM entities").fetchall()
            choices = {r[0]: r[1] for r in rows}
            raw_by_id = {r[0]: r[2] for r in rows}
            results = []
            for caption, score, entity_id in rp.extract(
                target, choices, scorer=fuzz.WRatio, score_cutoff=threshold
            ):
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
            for caption, score, entity_id in rp.extract(
                target, choices, scorer=fuzz.WRatio, score_cutoff=threshold
            ):
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


def os_web_url(dataset_name: str, target: str) -> str:
    """Return the OpenSanctions web search URL for a target within a dataset."""
    return f"https://www.opensanctions.org/search/?scope={dataset_name}&q={quote_plus(target)}"


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


def search_csv(path: Path, targets: list[str], rg_bin: str | None,
               use_fts: bool = True) -> dict[str, list[dict]]:
    """Search targets.simple.csv for each target. Returns {target: [row_dicts]}.

    use_fts=True (default): FTS5 index.
    use_fts=False: original grep/csv path.
    """
    if use_fts:
        index = ensure_index(path, "csv")
        return {target: search_fts_csv(index, target) for target in targets}

    # --- original grep/csv fallback path ---
    results: dict[str, list[dict]] = {t: [] for t in targets}
    seen_ids: set[str] = set()

    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        header_line = fh.readline().strip()
    fieldnames = [f.strip() for f in header_line.split(",")]

    for target in targets:
        raw_lines = grep_lines(path, target, rg_bin)
        for line in raw_lines:
            if line.strip().startswith(tuple(fieldnames[:1])):
                continue  # skip header lines that grep may return
            # Use StringIO to avoid CSV parser newline issues
            csv_text = header_line + "\n" + line
            reader = csv.DictReader(
                io.StringIO(csv_text),
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
        lines.append(f"  Identifiers : {identifiers}")

    aliases = row.get("aliases", "")
    if aliases:
        lines.append(f"  Aliases   : {aliases}")

    sanctions = row.get("sanctions", "")
    if sanctions:
        lines.append(f"  Sanctions : {sanctions}")

    lines.append(f"  Seen      : {first} → {last}")
    return "\n".join(lines)


def find_rg() -> str | None:
    """Return path to ripgrep binary, or None if not available."""
    for candidate in ("rg", "ripgrep"):
        try:
            subprocess.run([candidate, "--version"], capture_output=True, check=True)
            return candidate
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return None


def grep_lines(dataset: Path, pattern: str, rg_bin: str | None) -> list[str]:
    """Return raw lines from dataset matching pattern (case-insensitive)."""
    if rg_bin:
        cmd = [rg_bin, "-i", "-F", pattern, str(dataset)]
    else:
        cmd = ["grep", "-i", "-F", pattern, str(dataset)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return [l for l in result.stdout.splitlines() if l.strip()]
    except Exception as e:
        print(f"[warn] Search command failed: {e}", file=sys.stderr)
        return []


def parse_entity(line: str) -> dict | None:
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None


def prop(entity: dict, key: str) -> list[str]:
    """Safely get a property list from an FtM entity."""
    return entity.get("properties", {}).get(key, [])


def format_topics(topics: list[str]) -> str:
    labels = [RISK_TOPICS.get(t, t) for t in topics]
    return ", ".join(labels) if labels else "—"


def lookup_holder(holder_ids: list[str], dataset: Path, rg_bin: str | None) -> str:
    """Try to find the holder entity caption by ID."""
    if not holder_ids:
        return "—"
    holder_id = holder_ids[0]
    lines = grep_lines(dataset, holder_id, rg_bin)
    for line in lines:
        e = parse_entity(line)
        if e and e.get("id") == holder_id:
            return e.get("caption", holder_id)
    return holder_id


def format_entity(entity: dict, target: str, dataset: Path, rg_bin: str | None,
                  lookup_holders: bool = True) -> str:
    schema = entity.get("schema", "?")
    caption = entity.get("caption", "?")
    entity_id = entity.get("id", "?")
    datasets = ", ".join(entity.get("datasets", []))
    first_seen = entity.get("first_seen", "?")
    last_seen = entity.get("last_seen", "?")
    topics = prop(entity, "topics")
    topics_str = format_topics(topics)

    lines = [
        f"  Schema    : {schema}",
        f"  Caption   : {caption}",
        f"  ID        : {entity_id}",
        f"  Topics    : {topics_str}",
        f"  Datasets  : {datasets}",
    ]

    if schema == "CryptoWallet":
        public_keys = prop(entity, "publicKey")
        lines.append(f"  publicKey : {', '.join(public_keys) or '—'}")
        exchange = prop(entity, "managingExchange")
        if exchange:
            lines.append(f"  Exchange  : {', '.join(exchange)}")
        holder_ids = prop(entity, "holder")
        if holder_ids and lookup_holders:
            holder_name = lookup_holder(holder_ids, dataset, rg_bin)
            lines.append(f"  Holder    : {holder_name}  [{holder_ids[0]}]")
        elif holder_ids:
            lines.append(f"  Holder ID : {holder_ids[0]}")
        balance = prop(entity, "balance")
        if balance:
            currency = prop(entity, "currency")
            lines.append(f"  Balance   : {', '.join(balance)} {', '.join(currency)}")

    elif schema in ("Person",):
        names = prop(entity, "name") + prop(entity, "alias")
        if names:
            lines.append(f"  Names     : {'; '.join(names[:5])}")
        birth = prop(entity, "birthDate")
        if birth:
            lines.append(f"  Born      : {', '.join(birth)}")
        nationality = prop(entity, "nationality") or prop(entity, "citizenship")
        if nationality:
            lines.append(f"  Nation    : {', '.join(nationality)}")

    elif schema in ("Company", "Organization", "LegalEntity"):
        names = prop(entity, "name") + prop(entity, "alias")
        if names:
            lines.append(f"  Names     : {'; '.join(names[:5])}")
        country = prop(entity, "country") or prop(entity, "jurisdiction")
        if country:
            lines.append(f"  Country   : {', '.join(country)}")
        reg = prop(entity, "registrationNumber")
        if reg:
            lines.append(f"  Reg No.   : {', '.join(reg[:3])}")

    lines.append(f"  Seen      : {first_seen} → {last_seen}")
    return "\n".join(lines)


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

    # --- original grep fallback path (use_fts=False) ---
    raw_lines = grep_lines(dataset, target, rg_bin)
    entities = []
    seen_ids = set()

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

        # For CryptoWallet, verify the address is actually in publicKey (not just
        # a substring match anywhere in the line)
        if entity.get("schema") == "CryptoWallet":
            public_keys = [k.lower() for k in prop(entity, "publicKey")]
            if not any(target.lower() in k for k in public_keys):
                # Could be a holder ID match or other field; include anyway but note
                entity["_match_context"] = "indirect"
            else:
                entity["_match_context"] = "publicKey"
        else:
            entity["_match_context"] = "name_or_text"

        entities.append(entity)

    return entities


def main():
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
    parser.add_argument(
        "--no-fts",
        action="store_true",
        help="Disable FTS5 index; use original grep/substring search",
    )
    args = parser.parse_args()

    # Backwards compat: --dataset path/to/entities.ftm.json → force --file ftm
    if args.dataset and str(args.dataset).endswith(".ftm.json"):
        args.file = "ftm"
        dataset_path = Path(args.dataset).expanduser()
        dataset_dir = dataset_path.parent
    elif args.dataset:
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

    targets = list(args.targets)
    if args.targets_file:
        tf = Path(args.targets_file).expanduser()
        targets += [l.strip() for l in tf.read_text().splitlines() if l.strip()]

    if not targets:
        print("ERROR: No targets specified. Use --targets or --targets-file.", file=sys.stderr)
        sys.exit(1)

    rg_bin = find_rg()
    use_fts = not args.no_fts
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
            matches = search_target(target, active_file, args.schema, rg_bin, use_fts=use_fts)
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
        csv_results = search_csv(active_file, targets, rg_bin, use_fts=use_fts)
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
        names_results = search_names_txt(active_file, targets, rg_bin, use_fts=use_fts)
        hit_targets = [t for t, lines in names_results.items() if lines]

        for target, matched_lines in names_results.items():
            print(f"── Searching: {target}")
            if not matched_lines:
                print(f"  ❌ NO MATCH in names.txt")
                print(f"  Tip: rerun with --file ftm for full FtM detail")
                print()
                continue
            total_hits += len(matched_lines)
            match_label = "NAMES MATCH" if args.no_fts else "FTS MATCH"
            print(f"  ✅ {match_label} ({len(matched_lines)} line(s))")
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

    print(f"{'='*60}")
    print(f"Summary: {total_hits} total match(es) across {len(targets)} target(s)")
    print(f"{'='*60}\n")

    sys.exit(0 if total_hits > 0 else 2)


if __name__ == "__main__":
    main()
