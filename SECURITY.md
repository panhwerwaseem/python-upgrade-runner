# Security

An agent skill is instructions and code that your coding agent will follow and run. Review a skill before installing it, the same way you would review any dependency.

## What this skill does on your machine

| | |
|---|---|
| Reads | `compat_scan.py`: the `.py` files under the paths you give it, the names of files and folders next to them, and its rule table `compat_rules.json`. `stage_ledger.py`: its ledger file and the output of the command you give it |
| Writes | `compat_scan.py` writes nothing; it prints to stdout. `stage_ledger.py` writes the ledger file only: `.python-upgrade/ledger.json`, or the path passed to `--ledger` (and a `.tmp` file beside it while saving) |
| Executes | `compat_scan.py` executes nothing: scanned files are parsed with `ast`, never imported or run. `stage_ledger.py verify` runs the command you pass after `--`, directly, without a shell |
| Network | None. The bundled scripts import no network modules. `tools/validate.py` checks this in CI |
| Dependencies | Python standard library only |
| Pre-approved tools | None. `SKILL.md` has no `allowed-tools` entry, so your agent's normal permission prompts apply |
| Hooks, MCP servers, background processes | None |

The skill instructs the agent to edit your code and configuration as part of an upgrade, in stages, after recording a passing baseline. Those edits, and any package installs the agent proposes, go through your agent's normal review and permission flow.

`stage_ledger.py verify` runs whatever command it is given, with your user's permissions. It is meant for your test command. A test suite with side effects (sending email, writing to a shared database) has those side effects each time a stage is verified.

The ledger stores the verification command and the last 15 lines of its output. If your test output can contain secrets, keep the ledger out of version control; `.python-upgrade/` is in this repository's `.gitignore` for that reason.

`references/dependency-strategy.md` describes `pip` commands that contact a package index. The scripts never run them; the agent would, with your permission.

## Reporting a vulnerability

Please report security problems privately through the repository's **Security** tab ("Report a vulnerability"). If that option is not available, open an issue that says a private channel is needed, without including exploit details.

## Verifying what you install

- Install from a tagged release and read the diff between tags before updating.
- The whole skill is the `skills/python-upgrade-runner/` folder: one Markdown protocol, two Python scripts, one JSON rule table, three reference files, and eval fixtures.
- The fixture projects under `evals/files/` deliberately import modules that newer Python versions removed. They are test data. Nothing in this repository imports or runs them; the tests parse them with `ast`.
