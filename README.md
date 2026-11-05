# python-upgrade-runner

**An agent skill that runs a Python upgrade in stages: scan for what the target version removed, fix it before switching, and verify every stage with the test suite.**

Left alone, a coding agent asked to move a project to a newer Python tends to bump the version everywhere at once, run the tests, and patch whatever error comes first. When the run finally goes green it is often because a warning filter was added, a test was skipped, or a few unrelated "improvements" went in along the way. This skill replaces that with a protocol and two scripts: a passing baseline before any edit, one stage at a time with a recorded test result, the standard-library removals found up front with file, line and replacement, and no claim of success for an interpreter the tests never ran on.

Works with Claude Code, and with any agent that reads the open [Agent Skills](https://agentskills.io) format (Codex, Cursor, GitHub Copilot, Gemini CLI and others).

## What it looks like

Scanning a small project that runs on Python 3.9 for what breaks on 3.12:

```console
$ cd skills/python-upgrade-runner/evals/files/legacy-app
$ python3 ../../../scripts/compat_scan.py --target 3.12 .
compat_scan: target Python 3.12, 8 file(s) scanned, 161 rules for Python 3.8 to 3.14

BREAKS on Python 3.12 (8)
  inventory/config.py:2  collections.Mapping  [removed in 3.10]
      from collections import Mapping
      fix: collections.abc.Mapping
  inventory/config.py:3  configparser.SafeConfigParser  [removed in 3.12]
      from configparser import SafeConfigParser
      fix: configparser.ConfigParser
  inventory/plugins.py:2  imp  [removed in 3.12]
      import imp
      fix: importlib
  inventory/plugins.py:8  imp.load_source  [removed in 3.12]
      return imp.load_source(name, path)
      fix: importlib.util.spec_from_file_location(), importlib.util.module_from_spec() and spec.loader.exec_module()
  inventory/report.py:11  inspect.getargspec  [removed in 3.11]
      spec = inspect.getargspec(func)
      fix: inspect.signature() or inspect.getfullargspec()
  setup.py:1  distutils.core  [removed in 3.12]
      from distutils.core import setup
      fix: setuptools (setup and Extension import from setuptools)
  tests/test_config.py:18  unittest.TestCase.assertEquals  [removed in 3.12]
      self.assertEquals(settings["warehouse"], "main")
      fix: assertEqual
  tests/test_config.py:22  unittest.TestCase.assertEquals  [removed in 3.12]
      self.assertEquals(settings["low_stock"], "9")
      fix: assertEqual

Works on Python 3.12, breaks later or is deprecated (1)
  inventory/report.py:7  datetime.datetime.utcnow  [deprecated since 3.12]
      return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
      fix: datetime.datetime.now(datetime.timezone.utc); the result is timezone-aware, unlike utcnow()

Guarded by try/except or a version check: confirm the fallback path (1)
  inventory/compat.py:5  collections.Callable  [removed in 3.10]
      from collections import Callable
      fix: collections.abc.Callable

RESULT: 8 blocking finding(s) for Python 3.12. Each version's changes: https://docs.python.org/3/whatsnew/<version>.html
```

Recording the baseline, then trying to jump straight to 3.12:

```console
$ python3 ../../../scripts/stage_ledger.py open baseline --python 3.9
opened stage 1 'baseline'. Make this stage's changes, then run: stage_ledger.py verify -- <test command>
$ python3 ../../../scripts/stage_ledger.py verify -- python3 -m unittest discover -s tests
stage 1 'baseline': PASSED (exit code 0, attempt 1)
$ python3 ../../../scripts/stage_ledger.py open "python 3.12" --python 3.12
REFUSED: Python 3.12 skips versions after 3.9. Go one minor version at a time, or pass --skip-reason with the reason the user agreed to
$ python3 ../../../scripts/stage_ledger.py show
ledger: .python-upgrade/ledger.json
 #  stage                        python  status   runs last verification
 1  baseline                     3.9     passed   1    python3 -m unittest discover -s tests  (exit 0)
All 1 stage(s) passed. The next stage may be opened.
```

Trying to start the next stage on top of a failing one (the `mid-upgrade` fixture, whose 3.11 stage is red):

```console
$ python3 ../../../scripts/stage_ledger.py open "python 3.12" --python 3.12 --ledger ledger.json
REFUSED: stage 3 'python 3.11' is failing. Fix it and re-run verify until it passes; do not start another stage on top of a failing one
```

A project with nothing to report (the `clean-app` fixture). The scanner says what a clean result does and does not prove:

```console
$ python3 ../../../scripts/compat_scan.py --target 3.13 .
compat_scan: target Python 3.13, 6 file(s) scanned, 161 rules for Python 3.8 to 3.14

Not counted: the import resolves to a module in this project (1)
  cli.py:4  parser  [local module of the same name]
      import parser

RESULT: nothing blocking for Python 3.13. The table is not exhaustive: the proof is the test suite passing on Python 3.13 with -W error::DeprecationWarning.
```

## Install

Pick one route. Installing through more than one gives you the skill twice.

**Claude Code (plugin)**

```
/plugin install python-upgrade-runner --marketplace panhwerwaseem/python-upgrade-runner
```

On Claude Code versions before 2.1.275, use two steps:

```
/plugin marketplace add panhwerwaseem/python-upgrade-runner
/plugin install python-upgrade-runner@panhwerwaseem-python-upgrade-runner
```

**Any agent (skills CLI)**

```bash
npx skills add panhwerwaseem/python-upgrade-runner
```

**Manual**

Copy the `skills/python-upgrade-runner` folder into `.claude/skills/` (Claude Code) or `.agents/skills/` (cross-agent) in your project, or into the same folder under your home directory.

To pin a release, add the tag: `/plugin marketplace add panhwerwaseem/python-upgrade-runner#v0.1.0` or `npx skills add panhwerwaseem/python-upgrade-runner@v0.1.0`. Third-party plugins do not update automatically; run `claude plugin update python-upgrade-runner@panhwerwaseem-python-upgrade-runner` to update.

## Use

Describe the problem and the skill loads on its own:

> Move this service from Python 3.9 to 3.12. Tests run with `pytest -q`.

In Claude Code you can also call it directly with `/python-upgrade-runner`.

## What is in the skill

| File | Purpose |
|---|---|
| `SKILL.md` | The protocol: six hard rules and a six-step workflow from baseline to verified target |
| `scripts/compat_scan.py` | Parses every `.py` file with `ast` and reports imports and uses of standard-library modules and APIs that the target version removed or deprecated, with file, line, version and replacement. Uses inside `try/except ImportError` or a version check, warning filters that hide deprecations, and imports that resolve to the project's own modules are reported separately and do not block |
| `scripts/compat_rules.json` | The rule table, one rule per line, so it can be audited and extended. `compat_scan.py --list-rules` prints it |
| `scripts/stage_ledger.py` | Records each stage, runs its verification command, stores the result, and refuses to open a stage while the previous one is unverified or failing, or when it skips a minor version |
| `references/staged-method.md` | The stage order (baseline, tooling, removed-API fixes, dependencies, one minor version at a time, cleanup) and how to verify each |
| `references/breaking-changes.md` | Every rule in the table by Python version, plus changes the scanner cannot see, with pointers to the official What's New pages |
| `references/dependency-strategy.md` | How to find which packages block the target version and the order in which to move them |
| `evals/` | Four fixture projects (two with planted removals, one clean, one stopped mid-upgrade with a failing stage) with eval cases, plus trigger queries |

### What the scanner covers, and what it does not

The rule table holds removals and deprecations in the Python standard library from 3.8 through 3.14: removed modules such as `distutils`, `imp`, `asyncore`, `asynchat` and `smtpd` (3.12) and the PEP 594 modules (3.13), the `collections` ABC aliases (3.10), the `unittest` method aliases (3.12), and individual functions such as `inspect.getargspec` and `datetime.utcnow`. An entry is in the table only when its version is certain, so the table is not exhaustive.

It does not check third-party packages, methods called on objects (`thread.isAlive()`), removed parameters, behaviour changes, or non-Python files. It is not a Python 2 to 3 porting tool. A scan with nothing blocking is a starting point; the test suite on the target interpreter is the proof, and the protocol says so.

## Requirements

- Python 3.9 or later to run the scripts. The scanner analyses code written for any Python 3 version; files that use syntax newer than the interpreter running the scan are reported as not scanned.
- The interpreter for each stage you want verified. The skill tells the agent to report a stage as not verified when its interpreter is missing.
- No packages to install and no network access.

## What it reads, writes and contacts

- **Reads:** the `.py` files under the paths you pass to the scanner, its rule table, the ledger file, and the output of the verification command.
- **Writes:** the ledger file, `.python-upgrade/ledger.json` or the path passed to `--ledger`. Nothing else. The scanner only prints.
- **Runs:** only the verification command you pass to `stage_ledger.py verify` after `--`, directly, without a shell. The scanner never imports or executes the code it scans.
- **Contacts:** nothing. The scripts contain no network code; CI enforces this.
- **Permissions:** the skill pre-approves no tools. Your agent asks before running commands, as usual.

See [SECURITY.md](SECURITY.md).

## Testing status

- The scripts have unit tests that run in CI on Python 3.9 and 3.12, together with a validator for the skill format and plugin manifests. The tests run the scanner against every fixture and assert each planted finding and the clean result.
- The eval cases in `skills/python-upgrade-runner/evals/` are in the [skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) format. A with-skill versus without-skill score has not been published yet; results are welcome as an issue or pull request.

## Development

```bash
python3 tools/validate.py              # skill format, manifests, no-network check
python3 -m unittest discover -s tests  # script unit tests
```

To add a rule, add one line to `scripts/compat_rules.json` and the same name to `references/breaking-changes.md`; a test fails if the two disagree. Include a rule only when the official What's New page for that version confirms it.

## License

[MIT](LICENSE)
