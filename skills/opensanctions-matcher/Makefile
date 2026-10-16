SHELL := /bin/sh
BUMPVERSION := uvx --from bump2version bumpversion
PART ?= patch
SUMMARY ?= TODO: summarize the changes

.PHONY: version check-version bump bump-patch bump-minor bump-major bump-dry-run changelog-entry release-note release-preflight release release-patch release-minor release-major release-commit release-tag release-push

version:
	@python3 -c "from pathlib import Path; import re; text = Path('SKILL.md').read_text(encoding='utf-8'); m = re.search(r'^\\s+version:\\s*\"([0-9]+\\.[0-9]+\\.[0-9]+)\"\\s*$$', text, re.M); assert m, 'version not found in SKILL.md'; print(m.group(1))"

check-version:
	@python3 -c "from pathlib import Path; import re; skill = Path('SKILL.md').read_text(encoding='utf-8'); m = re.search(r'^\\s+version:\\s*\"([0-9]+\\.[0-9]+\\.[0-9]+)\"\\s*$$', skill, re.M); assert m, 'version not found in SKILL.md'; skill_version = m.group(1); file_version = Path('VERSION').read_text(encoding='utf-8').strip(); assert skill_version == file_version, f'version mismatch: SKILL.md={skill_version} VERSION={file_version}'; print(file_version)"

bump:
	$(BUMPVERSION) --allow-dirty --config-file .bumpversion.cfg $(PART)

bump-patch:
	$(MAKE) bump PART=patch

bump-minor:
	$(MAKE) bump PART=minor

bump-major:
	$(MAKE) bump PART=major

bump-dry-run:
	$(BUMPVERSION) --allow-dirty --config-file .bumpversion.cfg --dry-run --verbose $(PART)

changelog-entry:
	@python3 -c "from datetime import date; from pathlib import Path; import re; text = Path('SKILL.md').read_text(encoding='utf-8'); m = re.search(r'^\\s+version:\\s*\"([0-9]+\\.[0-9]+\\.[0-9]+)\"\\s*$$', text, re.M); version = m.group(1) if m else 'x.y.z'; print(f'## [{version}] - {date.today().isoformat()}\\n\\n### Added\\n- \\n')"

release-note:
	@python3 -c "from datetime import date; from pathlib import Path; import os; version = Path('VERSION').read_text(encoding='utf-8').strip(); summary = os.environ.get('SUMMARY', 'TODO: summarize the changes'); path = Path('CHANGELOG.md'); text = path.read_text(encoding='utf-8'); header = f'## [{version}] - {date.today().isoformat()}\\n\\n### Added\\n- {summary}\\n\\n'; marker = '## ['; idx = text.find(marker); assert idx >= 0, 'unexpected CHANGELOG.md format'; assert header not in text, 'release note already present'; path.write_text(text[:idx] + header + text[idx:], encoding='utf-8')"

release-preflight:
	@test -z "$$($(MAKE) -s --no-print-directory _git_status_short)" || { printf '%s\n' 'working tree must be clean before release'; $(MAKE) --no-print-directory _git_status_short; exit 1; }

release:
	$(MAKE) release-preflight
	$(MAKE) bump PART=$(PART)
	$(MAKE) release-note SUMMARY="$(SUMMARY)"
	$(MAKE) release-commit
	$(MAKE) release-tag
	$(MAKE) release-push

release-patch:
	$(MAKE) release PART=patch

release-minor:
	$(MAKE) release PART=minor

release-major:
	$(MAKE) release PART=major

release-commit:
	@version=$$($(MAKE) -s --no-print-directory version); git add SKILL.md VERSION CHANGELOG.md .bumpversion.cfg Makefile ../../AGENTS.md; git commit -m "chore: release opensanctions-matcher $$version"

release-tag:
	@version=$$($(MAKE) -s --no-print-directory version); git tag -a "v$$version" -m "OpenSanctions matcher $$version"

release-push:
	git push --follow-tags

_git_status_short:
	@git status --short
