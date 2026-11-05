---
name: python-upgrade-runner
description: Runs a Python runtime or major dependency upgrade in verified stages, scanning the code for standard-library modules and APIs removed at the target version, applying codemods before hand edits, and recording each stage's test result in a ledger. Use when upgrading or migrating a project to a newer Python version, when CI fails after a Python bump with ModuleNotFoundError for distutils, imp, cgi, asyncore or similar, when asked whether code is ready for a new Python, when clearing DeprecationWarning before an upgrade, or when the user says upgrade Python, bump the Python version, drop Python 3.8 support, or move to 3.12.
license: MIT
compatibility: Requires Python 3.9 or later to run the bundled scripts. No network access and no extra packages needed. Verifying a stage needs that stage's Python interpreter installed.
metadata:
  author: panhwerwaseem
  version: "0.1.0"
---

# Python upgrade runner

An upgrade is done when the project's own test suite passes on the target
interpreter with deprecation warnings treated as errors, every stage on the
way there has a passing verification in the ledger, and the diff contains
nothing but the upgrade. A clean scan is not done. A green run with warnings
filtered out is not done.

Paths in this file are relative to this skill's directory.

## Hard rules

1. **Green baseline before any change.** Do not edit a file until
   `scripts/stage_ledger.py` has recorded the test suite passing on the
   current interpreter. If the baseline fails, stop and tell the user which
   tests fail. Do not start an upgrade on a red suite.
2. **One stage at a time.** Open a stage, make only that stage's change,
   verify it. Never open the next stage while the ledger shows the current one
   as open or failing. Never edit or delete the ledger to get past a refusal,
   and never use `--skip-reason` without the user's agreement.
3. **Scan first, codemods before hand edits.** Run `scripts/compat_scan.py`
   before changing code. Apply a mechanical codemod in its own stage; make
   hand edits only for what remains. Do not mix the two in one change.
4. **The diff is the upgrade and nothing else.** No refactors, renames,
   reformatting, new features, or dependency bumps that the target does not
   require. List anything else you noticed under "Not done".
5. **Fix deprecations, never silence them.** Do not add a warnings filter,
   `-W ignore`, `PYTHONWARNINGS=ignore`, a pytest `filterwarnings` ignore
   entry, or a bare `except` to get a green run. Do not skip or delete a
   failing test. Do not pin the interpreter back and call it done.
6. **Verified means it ran on that interpreter.** Claim a stage passed only
   when the ledger records exit code 0 from the real test command, run on that
   stage's Python. If the interpreter is not installed, say so; do not record
   a run on another version under that stage's name. A scan with nothing
   blocking is not evidence that the code runs.

## Workflow

### 1. Establish the facts

Find and state: the Python version the project runs on today (CI config,
Dockerfile, `.python-version`, `requires-python`), the target version, the
exact test command, and which interpreters are installed
(`python3.11 --version` and so on). Ask if the target or the test command is
unclear.

### 2. Record the baseline

```bash
python3 scripts/stage_ledger.py open baseline --python <current>
python3 scripts/stage_ledger.py verify -- <test command on the current interpreter>
```

The ledger is written to `.python-upgrade/ledger.json`; pass `--ledger PATH`
before `--` to put it elsewhere. Note how many tests ran. A suite that runs
zero tests passes and proves nothing.

### 3. Scan against the final target

```bash
python3 scripts/compat_scan.py --target <target> <source and test paths>
```

Every finding names the file, line, the version where it breaks, and the
replacement. `removed` findings block. `later` and `deprecated` findings work
on the target but need fixing; `--fail-on warning` makes them block too.
`guarded` findings sit behind a `try/except ImportError` or a version check:
read both branches. `silenced` findings are warning filters that hide
deprecations: find out what each one hides. Run the scan with the newest
interpreter available so that newer syntax parses.
`references/breaking-changes.md` lists every rule and what the scanner cannot
see.

### 4. Plan the stages and show the user

Use the order in `references/staged-method.md`: tooling, removed-API fixes on
the current interpreter, dependencies, then one runtime stage per minor
version, then cleanup. Give the user the list of stages with the scanner's
findings assigned to them before editing.

### 5. Run each stage

```bash
python3 scripts/stage_ledger.py open "<stage name>" [--python <version>]
# make only this stage's change
python3 scripts/stage_ledger.py verify -- <test command>
```

- **Tooling.** Add the target to the CI matrix and test environments. No
  product code changes.
- **Removed-API fixes.** Still on the current interpreter. A codemod first,
  in its own stage, configured so its output still runs on the current
  version. Then hand edits for the remaining scanner findings. Re-run the
  scan; `removed` should be empty or explained.
- **Dependencies.** Find the packages that block the target and move each to
  a version that supports both interpreters, one major bump per stage. See
  `references/dependency-strategy.md`.
- **Runtime.** One minor version per stage, with `--python`. Verify with
  deprecations as errors:
  `<python for this stage> -W error::DeprecationWarning -m pytest` (or the
  project's equivalent). Read that version's What's New page for failures the
  scanner did not predict.
- **Cleanup.** On the target only: remove shims for dropped versions, raise
  `requires-python`, run syntax-modernising codemods in their own stage.

If `verify` fails, fix the cause inside the same stage and verify again. The
ledger keeps every attempt.

### 6. Report

```bash
python3 scripts/stage_ledger.py show
```

Give the user this, filled in from the script output:

```
Upgrade:        Python <from> to <to>
Baseline:       <test command>, <N> tests, passed on <from>
Scan:           <N> removed, <N> later or deprecated, <N> guarded, <N> silenced (target <to>)
Stages:         <ledger table from stage_ledger.py show>
Changes:        <per stage, what changed and where; codemod or hand edit>
Dependencies:   <package, old to new version, why the target required it>
Verified on:    <interpreters the test suite actually ran on, with the command>
Not verified:   <stages whose interpreter was not available, or anything not run>
Not done:       <remaining findings, filters left in place and why, things noticed but out of scope>
```

## Edge cases

- **The target interpreter is not installed.** Do the stages that run on the
  current interpreter, report the rest as not verified, and tell the user what
  to install or which CI job will run them. Do not claim the upgrade is done.
- **"Is this ready for 3.13?" with no upgrade asked for.** Run the scan,
  report the findings and what the scanner cannot see, and state that only a
  test run on 3.13 answers the question. Do not edit code.
- **CI already switched and is red.** Reproduce on the target, scan, then go
  back and record a baseline on the last interpreter that passed. Fix forward
  through stages; reverting the image is the user's decision, not a fix.
- **A warning comes from a third-party package.** That is a dependency
  finding. Upgrade the package; if no fixed release exists, a filter limited
  to that package and message is acceptable with the user's agreement, and it
  goes in the report.
- **`import distutils` works on 3.12.** Setuptools provides its own copy when
  installed. The scanner still reports it: the project is depending on
  setuptools without declaring it.
- **A file fails to parse.** The scanner reports it as not scanned and exits 1.
  Re-run with a newer interpreter, or `--exclude` it and say so in the report.
- **A major dependency upgrade without a Python change.** Use the same
  ledger and stage discipline without `--python`. The scanner covers the
  standard library only; use the dependency's own migration guide and codemod.
- **`.python-upgrade/`** is working state. Ask before committing it.
