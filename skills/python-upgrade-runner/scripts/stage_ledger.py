#!/usr/bin/env python3
"""Keep a ledger of upgrade stages and the verification result of each one.

An upgrade is a sequence of stages (baseline, tooling, codemods, one Python
minor version, a dependency, cleanup). Each stage is closed by a verification
command that passes. The ledger records every attempt and refuses to open the
next stage while the current one has no passing verification.

Commands:
  open NAME       Open the next stage. The first stage must be named "baseline".
                  Refused while the current stage is unverified or failing.
  verify -- CMD   Run CMD directly (no shell) as the verification of the
                  current stage. Records the command, exit code, duration and
                  the last lines of output.
  show            Print the ledger.

Examples:
  stage_ledger.py open baseline --python 3.9
  stage_ledger.py verify -- python3.9 -m pytest -q
  stage_ledger.py open "python 3.10" --python 3.10
  stage_ledger.py verify -- python3.10 -W error::DeprecationWarning -m pytest -q
  stage_ledger.py show --json

Put options before "--"; everything after it is the command.

Exit codes: 0 = stage opened, verification passed, or every stage has passed;
1 = open refused, verification failed, or the current stage has not passed;
2 = usage or input error.
Standard library only. Makes no network calls. Writes only the --ledger file.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time

DEFAULT_LEDGER = os.path.join(".python-upgrade", "ledger.json")
TAIL_LINES = 15


class LedgerError(Exception):
    """Unusable input: exit code 2."""


def parse_python(text):
    parts = text.strip().split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise LedgerError("--python takes a version such as 3.12, not %r" % text)
    return int(parts[0]), int(parts[1])


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path, must_exist=True):
    if not os.path.isfile(path):
        if must_exist:
            raise LedgerError("no ledger at %s; start with: stage_ledger.py open baseline" % path)
        return {"version": 1, "stages": []}
    try:
        with open(path, encoding="utf-8") as handle:
            ledger = json.load(handle)
        for stage in ledger["stages"]:
            missing = [key for key in ("id", "name", "verifications") if key not in stage]
            missing += [key for attempt in stage.get("verifications", [])
                        for key in ("command", "exit_code", "passed") if key not in attempt]
            if missing:
                raise ValueError("a stage lacks %s" % ", ".join(sorted(set(missing))))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise LedgerError("cannot read ledger %s: %s" % (path, exc))
    return ledger


def save(path, ledger):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(ledger, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def status_of(stage):
    """open = never verified, passed or failing = result of the latest verification."""
    if not stage["verifications"]:
        return "open"
    return "passed" if stage["verifications"][-1]["passed"] else "failing"


def refusal(ledger, name, python, skip_reason):
    """Why a new stage may not be opened now, or None if it may."""
    stages = ledger["stages"]
    if not stages:
        if name.strip().lower() != "baseline":
            return ("the first stage must be named 'baseline': record the test suite passing on "
                    "the current interpreter before changing anything")
        return None
    current = stages[-1]
    state = status_of(current)
    if state == "open":
        return ("stage %d '%s' has not been verified. Run: stage_ledger.py verify -- <test command>"
                % (current["id"], current["name"]))
    if state == "failing":
        return ("stage %d '%s' is failing. Fix it and re-run verify until it passes; "
                "do not start another stage on top of a failing one" % (current["id"], current["name"]))
    previous = [parse_python(s["python"]) for s in stages if s.get("python")]
    if python and previous:
        last = previous[-1]
        if python < last:
            return "Python %d.%d is older than the %d.%d already recorded" % (python + last)
        if (python[0] != last[0] or python[1] > last[1] + 1) and not skip_reason:
            return ("Python %d.%d skips versions after %d.%d. Go one minor version at a time, or "
                    "pass --skip-reason with the reason the user agreed to" % (python + last))
    return None


def cmd_open(args, ledger):
    python = parse_python(args.python) if args.python else None
    reason = refusal(ledger, args.name, python, args.skip_reason)
    if reason:
        return 1, "REFUSED: " + reason
    stage = {"id": len(ledger["stages"]) + 1, "name": args.name.strip(), "python": args.python,
             "note": args.note, "skip_reason": args.skip_reason, "opened_at": now(),
             "verifications": []}
    ledger["stages"].append(stage)
    save(args.ledger, ledger)
    return 0, "opened stage %d '%s'. Make this stage's changes, then run: stage_ledger.py verify -- <test command>" % (
        stage["id"], stage["name"])


def cmd_verify(args, ledger):
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise LedgerError("give the verification command after --")
    if not ledger["stages"]:
        raise LedgerError("no stage is open; start with: stage_ledger.py open baseline")
    stage = ledger["stages"][-1]
    started = time.time()
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=args.timeout)
        output, exit_code = proc.stdout.decode("utf-8", errors="replace"), proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"").decode("utf-8", errors="replace")
        output += "\n[stage_ledger] command exceeded --timeout of %s seconds" % args.timeout
        exit_code = None
    except OSError as exc:
        raise LedgerError("cannot run %r: %s" % (command[0], exc))
    tail = [line.rstrip()[:300] for line in output.splitlines() if line.strip()][-TAIL_LINES:]
    passed = exit_code == 0
    stage["verifications"].append({
        "command": command, "exit_code": exit_code, "passed": passed,
        "duration_s": round(time.time() - started, 1), "at": now(), "output_tail": tail,
    })
    save(args.ledger, ledger)
    lines = ["stage %d '%s': %s (exit code %s, attempt %d)" % (
        stage["id"], stage["name"], "PASSED" if passed else "FAILED", exit_code,
        len(stage["verifications"]))]
    if not passed:
        lines.extend("    " + line for line in tail)
        lines.append("Fix this stage and run verify again. Do not open another stage.")
    return (0 if passed else 1), "\n".join(lines)


def describe(ledger):
    """Ledger plus the computed status of each stage; the --json output."""
    stages = [dict(stage, status=status_of(stage)) for stage in ledger["stages"]]
    current = stages[-1] if stages else None
    return {
        "stages": stages,
        "current_stage": current["id"] if current else None,
        "current_status": current["status"] if current else None,
        "all_passed": bool(stages) and all(stage["status"] == "passed" for stage in stages),
    }


def render(view, path):
    lines = ["ledger: %s" % path, " #  %-28s %-7s %-8s %-4s %s" % ("stage", "python", "status", "runs", "last verification")]
    for stage in view["stages"]:
        last = stage["verifications"][-1] if stage["verifications"] else None
        command = "%s  (exit %s)" % (" ".join(last["command"]), last["exit_code"]) if last else "-"
        lines.append("%2d  %-28s %-7s %-8s %-4d %s" % (
            stage["id"], stage["name"][:28], stage.get("python") or "-",
            stage["status"].upper() if stage["status"] != "passed" else "passed",
            len(stage["verifications"]), command))
        if stage.get("skip_reason"):
            lines.append("    skipped versions: %s" % stage["skip_reason"])
    if not view["stages"]:
        lines.append("(no stages yet)")
    elif view["all_passed"]:
        lines.append("All %d stage(s) passed. The next stage may be opened." % len(view["stages"]))
    else:
        current = view["stages"][-1]
        if current["status"] == "failing":
            lines.extend("    " + line for line in current["verifications"][-1].get("output_tail", []))
        lines.append("Stage %d '%s' is %s. No new stage until it passes." % (
            current["id"], current["name"], current["status"].upper()))
    return "\n".join(lines)


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ledger", default=DEFAULT_LEDGER,
                        help="ledger file (default: %s)" % DEFAULT_LEDGER)
    common.add_argument("--json", action="store_true", help="print the ledger as JSON")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="action")
    opener = commands.add_parser("open", parents=[common], help="open the next stage")
    opener.add_argument("name", help='stage name, for example baseline or "python 3.11"')
    opener.add_argument("--python", help="interpreter version this stage is verified on, for example 3.11")
    opener.add_argument("--note", default="", help="what this stage changes")
    opener.add_argument("--skip-reason", default="",
                        help="why this stage jumps more than one minor version; recorded in the ledger")
    verifier = commands.add_parser("verify", parents=[common], help="run the verification command")
    verifier.add_argument("--timeout", type=float, default=3600.0,
                          help="seconds before the command is killed and counted as failed (default 3600)")
    verifier.add_argument("command", nargs=argparse.REMAINDER, help="the command, after --")
    commands.add_parser("show", parents=[common], help="print the ledger")
    args = parser.parse_args(argv)
    if not args.action:
        parser.error("choose a command: open, verify or show")

    try:
        ledger = load(args.ledger, must_exist=args.action != "open")
        if args.action == "open":
            code, message = cmd_open(args, ledger)
        elif args.action == "verify":
            code, message = cmd_verify(args, ledger)
        else:
            view = describe(ledger)
            code, message = (0 if view["all_passed"] else 1), render(view, args.ledger)
    except LedgerError as exc:
        print("stage_ledger.py: error: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        result = describe(ledger)
        if args.action != "show":
            result["message"] = message
        print(json.dumps(result, indent=2))
    else:
        print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
