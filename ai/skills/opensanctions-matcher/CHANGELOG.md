# Changelog

All notable changes to the opensanctions-matcher skill will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-12

### Added
- **FTS5 full-text search** — SQLite FTS5 as default search engine with unicode61 tokenizer
  - Transparent index build on first run, auto-rebuild when source is newer
  - Separate `.fts5.db` index per dataset file for fast searching
- **Fuzzy matching layer** — Optional `--fuzzy [THRESHOLD]` for approximate matching
  - Uses rapidfuzz WRatio scorer to find typos, transliterations, OCR errors
  - Performance warning on large datasets (>500k entries)
- **`--no-fts` fallback** — Original grep/substring search for backward compatibility
- **Three file type support** — names.txt, targets.simple.csv, entities.ftm.json
- **Names-first two-phase search** — Searches names first, enriches with CSV/JSON on hit
- **Two-layer index strategy** — Build once, rebuild on source update, bypass with --no-fts
- **FTS5 query strategy** — Phrase search (multi-word), prefix search (single word), exact (crypto addresses)
- **Skill integration** — Works with Claude Code, Codex, Gemini via shared ai/skills/ directory
- **Automatic dataset selection** — Identifies target type and selects most relevant OpenSanctions dataset
- **Cache management** — Checks local cache, offers to download if missing
- **Full test coverage** — 63 unit and integration tests
- **Comprehensive documentation** — Design specs, implementation plans, reference guides

### Technical Stack
- Python 3.10+
- SQLite3 (stdlib)
- rapidfuzz (optional, for fuzzy matching)
- ripgrep/grep (optional, for --no-fts fallback)

---

## Release Notes

### v1.0.0 (Initial Release)
Complete implementation of FTS5-based sanctions screening skill with:
- Fast, ranked search via SQLite FTS5
- Optional fuzzy matching for approximate hits
- Automatic dataset selection and cache management
- Full FtM entity context in results
- Integration with Claude Code, Codex, Gemini
- Comprehensive test suite (63 tests, all passing)
