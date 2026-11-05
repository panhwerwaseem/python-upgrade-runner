# Dependency strategy

How to find which packages block a target Python version, and the order in
which to move them. `scripts/compat_scan.py` does not look at third-party
packages; this is the manual part of the upgrade.

The commands below contact a package index. Run them only where the user
allows network access, and say so when you could not.

## Contents

- [Why a package blocks](#why-a-package-blocks)
- [Find the blockers](#find-the-blockers)
- [Order of work](#order-of-work)
- [When a dependency has no release for the target](#when-a-dependency-has-no-release-for-the-target)
- [Removed modules that dependencies used to provide by accident](#removed-modules-that-dependencies-used-to-provide-by-accident)
- [What to record](#what-to-record)

## Why a package blocks

| Reason | How it shows up |
|---|---|
| Its metadata excludes the target | The installer reports that no version matches, or names `Requires-Python` |
| No built wheel for the target | The installer falls back to building from source and fails, usually on a C extension |
| It installs but uses a removed module | ImportError or ModuleNotFoundError at import time, for example for `distutils`, `imp` or `pkg_resources` |
| It installs and imports but warns | DeprecationWarning from inside the package when the tests run with warnings as errors |

A pure-Python package (wheel tag `py3-none-any`) installs on any Python 3,
so the first two reasons rarely apply to it; the last two still can. A
package with compiled code needs a wheel built for the target's tag (for
example `cp313`) or for the stable ABI (`abi3`).

## Find the blockers

Work from the project's own declaration of its dependencies (lock file,
`requirements*.txt`, `pyproject.toml`), not from whatever is installed.

1. **Try to resolve on the target.** In a fresh virtual environment created
   by the target interpreter:

   ```bash
   python3.13 -m venv /tmp/py313-check
   /tmp/py313-check/bin/python -m pip install --dry-run -r requirements.txt
   ```

   `--dry-run` resolves without installing. It needs a recent pip; check
   `pip install --help`. Every package the resolver rejects is a blocker.

2. **Without the target interpreter**, ask for wheels only:

   ```bash
   pip download --only-binary=:all: --python-version 3.13 --no-deps -d /tmp/wheels -r requirements.txt
   ```

   A package with no wheel for that version fails here. This does not prove
   the package works, only that a build exists.

3. **Read the metadata of each direct dependency**: the `Requires-Python`
   field and the `Programming Language :: Python :: 3.x` classifiers on its
   index page, and its changelog for the release that added support for the
   target. Classifiers are informational and are sometimes out of date in
   both directions.

4. **Find who pulls in a transitive blocker.** `pip show <package>` lists
   `Required-by`. The fix is usually to upgrade the direct dependency that
   requires it.

5. **Check for consistency after installing**: `pip check` reports installed
   packages whose requirements are not met.

Write the result as a table before changing anything:

| Package | Pinned now | First version supporting the target | Supports the current Python too | Major bump |
|---|---|---|---|---|

## Order of work

1. **Prefer a version that supports both interpreters.** Upgrade to it while
   still on the current Python, in its own ledger stage, and verify. This is
   the dependency stage of `references/staged-method.md`.
2. **One major bump per stage.** A new major version of a framework is its own
   upgrade. Read its migration guide, apply its codemod if it ships one, and
   verify before touching the next package.
3. **When no single version supports both**, use environment markers so each
   interpreter gets a version that works, then remove the old branch in the
   cleanup stage:

   ```
   somepackage<2 ; python_version < "3.10"
   somepackage>=2 ; python_version >= "3.10"
   ```

4. **Backports go the other way.** A marker such as
   `tomli ; python_version < "3.11"` installs a backport only where the
   standard library lacks the module. After the upgrade these become dead
   weight; remove them in cleanup together with their `try/except ImportError`
   import.
5. **Regenerate the lock file on the target interpreter** (pip-tools, Poetry,
   uv, or whichever tool the project uses). A lock resolved on the old
   interpreter can pin versions that do not install on the new one. Review
   the lock diff: only the packages you meant to move should have moved.

## When a dependency has no release for the target

In order of preference:

1. Wait, and upgrade to the newest Python the dependency does support. Report
   the blocker by name and version.
2. Replace it, if it is unmaintained and the usage is small. This is a
   separate change that the user must agree to.
3. Vendor or patch it. Last resort; it makes the project the maintainer.

Do not install a pre-release, a fork, or a build from an unreviewed source to
get a green run without the user's agreement.

## Removed modules that dependencies used to provide by accident

- From Python 3.12, a new virtual environment no longer contains
  `setuptools`. Code and dependencies that import `pkg_resources` or
  `distutils` without declaring `setuptools` fail on a clean install even if
  they worked on a developer machine that had it.
- Installing `setuptools` makes `import distutils` work again on 3.12 and
  later, because setuptools ships its own copy. Treat that as a stopgap for a
  dependency you do not control, declare it explicitly, and do not rely on it
  in the project's own code.
- A package on the index that restores a removed standard-library module is a
  third-party dependency like any other. Adding one is a decision for the
  user; the default is to move to the replacement listed in
  `references/breaking-changes.md`.

## What to record

For each dependency stage, the report needs: the package, the old and new
version, why the target required the change, and the verification result.
A dependency that was bumped but was not required by the target does not
belong in the upgrade.
