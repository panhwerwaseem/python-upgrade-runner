# The staged upgrade method

An upgrade done as one large change fails in ways that cannot be separated:
a removed module, a dependency that has no build for the new interpreter, and
an unrelated refactor all show up in the same red test run. Staging keeps each
cause in its own small change with its own passing test run.

Every stage follows the same loop:

1. `stage_ledger.py open "<name>"`
2. Make only this stage's change.
3. `stage_ledger.py verify -- <test command>`
4. If it fails, fix it inside this stage and verify again. Do not move on.
5. Commit the stage on its own (if the user wants commits).

## Contents

- [Stage order](#stage-order)
- [1. Baseline](#1-baseline)
- [2. Tooling](#2-tooling)
- [3. Removed-API fixes on the current interpreter](#3-removed-api-fixes-on-the-current-interpreter)
- [4. Dependencies](#4-dependencies)
- [5. Runtime, one minor version at a time](#5-runtime-one-minor-version-at-a-time)
- [6. Cleanup](#6-cleanup)
- [The verification command](#the-verification-command)
- [Codemods](#codemods)
- [What does not belong in an upgrade](#what-does-not-belong-in-an-upgrade)

## Stage order

| Stage | Interpreter | Change |
|---|---|---|
| Baseline | current | None. Record the suite passing |
| Tooling | current | CI, linters and test environments learn about the target |
| Removed-API fixes | current | Replace names the target removes with ones that work on both versions |
| Dependencies | current | Move each blocking package to a version that supports both interpreters |
| Runtime | next minor, repeated | Switch the interpreter; fix what only shows up there |
| Cleanup | target | Drop shims for old versions, modernise syntax, update metadata |

The order matters. Stages 2 to 4 happen on the interpreter that already
works, so a failure there is caused by the change just made and nothing else.
By the time the interpreter changes, most of the breakage is already fixed.

## 1. Baseline

Run the full test suite on the current interpreter, unchanged, and record it:

```bash
python3 scripts/stage_ledger.py open baseline --python 3.9
python3 scripts/stage_ledger.py verify -- python3.9 -m pytest -q
```

If the baseline is red, stop. An upgrade started on a failing suite cannot
tell its own breakage from what was already broken. Tell the user which tests
fail and let them decide: fix first, or agree an explicit list of known
failures that every later stage is compared against.

Also record, in the stage note or the report: the number of tests run, and
whether the suite prints deprecation warnings today. A suite that runs zero
tests passes, and proves nothing.

## 2. Tooling

Make the project able to run on both versions before any product code
changes:

- CI: add the target (and each intermediate version) to the test matrix. It
  may fail at first; that is the list of work.
- Test environments: `tox.ini` `envlist`, `noxfile.py`, Docker images used
  for tests.
- Linters and formatters that pin a Python version: for example
  `target-version` for ruff and black, `python_version` for mypy.
- Do not change `requires-python`, the runtime Docker image, or
  `.python-version` yet. Those switch in the runtime stage.

## 3. Removed-API fixes on the current interpreter

Run the scanner against the final target:

```bash
python3 scripts/compat_scan.py --target 3.12 src tests
```

Almost every replacement in `references/breaking-changes.md` already exists
on older versions (`collections.abc`, `importlib`, `shlex.quote`,
`assertEqual`). Apply those now, while the suite still runs on the current
interpreter. Use a codemod where one exists (see [Codemods](#codemods)), in
its own stage, then make the remaining edits by hand.

A replacement that only exists on newer versions (for example
`locale.getencoding()`, added in 3.11) waits for the runtime stage that
introduces it.

Re-run the scanner after the edits. `removed` findings for the target should
be gone or explained.

## 4. Dependencies

Find the packages that block the target and move each one to a version that
supports both the current and the target interpreter. One stage per major
version bump of a package, because a major bump is its own upgrade with its
own breaking changes. `references/dependency-strategy.md` has the method.

## 5. Runtime, one minor version at a time

For each minor version between current and target:

```bash
python3 scripts/stage_ledger.py open "python 3.10" --python 3.10
python3 scripts/stage_ledger.py verify -- python3.10 -W error::DeprecationWarning -m pytest -q
```

Going one version at a time matters because each What's New page describes
the changes from the previous version only, and because the deprecation
warnings seen on one version are the removals of a later one. A failure on
3.10 has one page of candidate causes. A failure after jumping from 3.9 to
3.13 has four.

The ledger refuses a jump of more than one minor version unless it is given
`--skip-reason`. Use that only when an intermediate interpreter cannot be
obtained, and only with the user's agreement. The trade-off: causes from the
skipped versions arrive together.

If an interpreter for a stage is not installed, say so. Do not record a run
on a different interpreter under that stage's name.

Switch the things that select the interpreter in this stage: the CI default,
the runtime Docker image, `.python-version`. Keep the old version in the test
matrix until the cleanup stage.

## 6. Cleanup

Only after the suite passes on the target:

- Remove compatibility shims for versions no longer supported: `try/except
  ImportError` fallbacks, `sys.version_info` branches, backport packages and
  their environment markers. The scanner's `guarded` findings are the list.
- Raise `requires-python`, update trove classifiers, and drop the old version
  from the CI matrix.
- Run syntax-modernising codemods now, in a stage of their own.
- Remove any warning filter that was only there for the old version.

## The verification command

Use the project's real test command, on the interpreter the stage is about.
Name the interpreter explicitly (`python3.11 -m pytest`, or the tox
environment) so the ledger shows which one ran.

Make deprecations fail, at least on the runtime stages:

| How | Effect |
|---|---|
| `python -W error::DeprecationWarning -m pytest` | A DeprecationWarning raised while the tests run becomes an error |
| `filterwarnings = error::DeprecationWarning` in the pytest configuration | The same, for every run |
| `PYTHONWARNINGS=error::DeprecationWarning` | The same, for subprocesses too |
| `python -X dev` | Development mode: shows warnings that are hidden by default, without failing |

If turning warnings into errors fails inside a third-party package, that is a
dependency finding (stage 4), not a reason to drop the flag. Narrow the filter
to that one package and message, and record it in the report.

Also compile every file on the target interpreter. It catches syntax errors
and prints SyntaxWarning for things like invalid escape sequences in files the
tests never import:

```bash
python3.12 -m compileall -q src tests
```

## Codemods

A codemod is a tool that rewrites code mechanically. Use one before editing
by hand: it is consistent, and its diff is easy to review because every
change has the same shape.

- **pyupgrade** rewrites old idioms to newer ones for a minimum version given
  as `--py3N-plus` (for example `--py310-plus`). It takes file names.
- **ruff** has the same family of rewrites under the `UP` rule prefix:
  `ruff check --select UP --fix`, with the minimum version set by
  `target-version` in its configuration.
- Flags and rule sets differ between releases. Check each tool's `--help`
  for the installed version.

Two rules for using them in an upgrade:

1. **A codemod gets its own stage.** Run it, review the diff, verify, commit.
   Never mix its output with hand edits in the same change.
2. **Mind which direction it points.** A rewrite to syntax that only the
   target understands breaks the current interpreter. Before the runtime
   switch, run codemods with the *current* version as the minimum, so they
   produce only code the current interpreter can run. Run them with the
   target as the minimum in the cleanup stage.

Codemods do not replace removed modules such as `imp`, `distutils` or `cgi`.
Those are hand edits guided by the scanner.

## What does not belong in an upgrade

- Refactors, renames, reformatting, or new features, however tempting the
  file looks while it is open.
- Dependency bumps that the target does not require.
- Deleting or skipping tests that fail on the target.
- Warning filters, `-W ignore`, or `PYTHONWARNINGS=ignore` added to get a
  green run.
- Pinning the interpreter back to the old version and calling the task done.

If something outside the upgrade needs doing, list it in the report under
"Not done" and leave the code alone.
