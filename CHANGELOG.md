# Changelog

All notable changes to this skill are recorded here. Versions follow [Semantic Versioning](https://semver.org).

## 0.1.0 - 2026-11-06

### Added

- `SKILL.md` with the upgrade protocol: six hard rules and a six-step staged workflow.
- `scripts/compat_scan.py`, an `ast`-based scanner for standard-library modules and APIs removed or deprecated at a target Python version, with guarded, silenced and shadowed findings reported separately.
- `scripts/compat_rules.json`, the rule table the scanner reads, covering removals in Python 3.8 through 3.14.
- `scripts/stage_ledger.py`, a ledger that records each stage's verification command and result and refuses to open a stage on top of an unverified or failing one.
- References for the staged method, breaking changes by version, and dependency strategy.
- Four fixture projects (two with planted removals, one clean, one stopped mid-upgrade) with eval cases, plus trigger queries.
- Unit tests, a format validator, and a CI workflow.
