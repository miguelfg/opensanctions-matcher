SHELL := /bin/sh
BUMPVERSION := uvx --from bump2version bumpversion
PART ?= patch

.PHONY: version check-version bump bump-patch bump-minor bump-major bump-dry-run changelog-entry

version:
	@python3 -c "from pathlib import Path; import re; text = Path('SKILL.md').read_text(encoding='utf-8'); m = re.search(r'^version:\\s*([0-9]+\\.[0-9]+\\.[0-9]+)\\s*$$', text, re.M); assert m, 'version not found in SKILL.md'; print(m.group(1))"

check-version:
	@python3 -c "from pathlib import Path; import re; skill = Path('SKILL.md').read_text(encoding='utf-8'); m = re.search(r'^version:\\s*([0-9]+\\.[0-9]+\\.[0-9]+)\\s*$$', skill, re.M); assert m, 'version not found in SKILL.md'; skill_version = m.group(1); file_version = Path('VERSION').read_text(encoding='utf-8').strip(); assert skill_version == file_version, f'version mismatch: SKILL.md={skill_version} VERSION={file_version}'; print(file_version)"

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
	@python3 -c "from datetime import date; from pathlib import Path; import re; text = Path('SKILL.md').read_text(encoding='utf-8'); m = re.search(r'^version:\\s*([0-9]+\\.[0-9]+\\.[0-9]+)\\s*$$', text, re.M); version = m.group(1) if m else 'x.y.z'; print(f'## [{version}] - {date.today().isoformat()}\\n\\n### Added\\n- \\n')"
