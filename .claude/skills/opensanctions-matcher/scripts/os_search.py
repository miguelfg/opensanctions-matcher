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
    return source.stat().st_mtime > index.stat().st_mtime


def fts_query(target: str) -> str:
    """Build a FTS5 MATCH expression for target.

    Multi-word → phrase search "word1 word2"
    Crypto addr (single token >= 20 alnum chars) → exact, no prefix suffix
    Single alnum word → exact OR prefix* for partial-input tolerance
    Single word with special chars → quoted phrase (safe fallback)
    """
    stripped = target.strip()
    if " " in stripped:
        return '"' + stripped.replace('"', '""') + '"'
    if len(stripped) >= 20 and stripped.isalnum():
        return stripped
    if stripped.isalnum():
        return f"{stripped} OR {stripped}*"
    return '"' + stripped.replace('"', '""') + '"'


def os_web_url(dataset_name: str, target: str) -> str:
    """Return the OpenSanctions web search URL for a target within a dataset."""
    return f"https://www.opensanctions.org/search/?scope={dataset_name}&q={quote_plus(target)}"


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


def search_csv(path: Path, targets: list[str], rg_bin: str | None) -> dict[str, list[dict]]:
    """Search targets.simple.csv for each target. Returns {target: [row_dicts]}.

    Uses rg/grep for fast pre-filtering, then parses matching lines with csv.DictReader.
    Missing columns are returned as empty strings (DictReader restval default).
    """
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
                  rg_bin: str | None) -> list[dict]:
    """Find all entities matching target string in the dataset."""
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
                        print(f"  Web URL   : {os_web_url(dataset_name, target)}")
                        print()

    print(f"{'='*60}")
    print(f"Summary: {total_hits} total match(es) across {len(targets)} target(s)")
    print(f"{'='*60}\n")

    sys.exit(0 if total_hits > 0 else 2)


if __name__ == "__main__":
    main()
