#!/usr/bin/env python3
"""Find standard-library modules and APIs that a target Python removes or deprecates.

Each .py file is parsed with ast. Nothing is imported or executed. Imports,
attribute uses and unittest method aliases are matched against the rule table
in compat_rules.json. Every finding names the file, the line, the version
where the name breaks, and the replacement.

Statuses:
  removed     Gone at the target version. Blocking.
  later       Still present at the target, removed in a later version.
  deprecated  Deprecated at the target; the table has no removal version.
  silenced    A warnings filter that ignores DeprecationWarning.
  guarded     Inside try/except ImportError or AttributeError, or under a
              version or hasattr check. Listed for review, never blocking.
  shadowed    The import resolves to a module in the scanned project, not the
              standard library. Listed so it can be checked, never blocking.

Examples:
  compat_scan.py --target 3.12 src tests
  compat_scan.py --target 3.13 --fail-on warning --exclude 'vendor/*' .
  compat_scan.py --target 3.12 --json . > scan.json
  compat_scan.py --list-rules

The table is not exhaustive and covers the standard library only. Nothing
blocking does not prove the code runs on the target; the test suite passing on
the target interpreter does. Files this interpreter cannot parse (for example
syntax newer than the Python running the scan) count as blocking.

Exit codes: 0 = nothing blocking, 1 = blocking findings or files that could
not be parsed, 2 = usage or input error.
Standard library only. Reads files only. Makes no network calls.
"""
import argparse
import ast
import fnmatch
import json
import os
import sys

RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compat_rules.json")
WHATS_NEW = "https://docs.python.org/3/whatsnew/%s.html"
SKIP_DIRS = ("__pycache__", "node_modules", "site-packages")
GUARD_EXCEPTIONS = ("ImportError", "ModuleNotFoundError", "AttributeError", "Exception", "BaseException")
# function -> position of its "category" argument
WARNING_FILTERS = {"warnings.filterwarnings": 2, "warnings.simplefilter": 1}
SILENCED_RULE = {
    "name": "warnings-filter", "kind": "check", "removed_in": None, "deprecated_in": None,
    "replacement": "Fix the deprecated call this filter hides, then delete the filter or narrow it "
                   "to one named third-party warning",
}
WARNING_STATUSES = ("later", "deprecated", "silenced")


def parse_version(text):
    """'3.12' or '3.12.4' -> (3, 12). Raises ValueError for anything else."""
    parts = str(text).strip().split(".")
    if not 2 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
        raise ValueError("%r is not a Python version such as 3.12" % text)
    return int(parts[0]), int(parts[1])


def show_version(version):
    return "%d.%d" % version if version else None


def load_rules(path):
    """Read and check the rule table. Raises ValueError with a clear message."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read rule table %s: %s" % (path, exc))
    table = {"rules": {}, "methods": {}}
    try:
        table["first"] = parse_version(data["covers"]["first"])
        table["last"] = parse_version(data["covers"]["last"])
        for raw in data["rules"]:
            rule = {
                "name": raw["name"], "kind": raw["kind"], "replacement": raw["replacement"],
                "removed_in": parse_version(raw["removed_in"]) if raw.get("removed_in") else None,
                "deprecated_in": parse_version(raw["deprecated_in"]) if raw.get("deprecated_in") else None,
            }
            is_method = rule["kind"] == "method"
            group = table["methods"] if is_method else table["rules"]
            key = rule["name"].rsplit(".", 1)[-1] if is_method else rule["name"]
            if (rule["kind"] not in ("module", "api", "method") or key in group
                    or not rule["replacement"].strip()
                    or (rule["removed_in"] is None and rule["deprecated_in"] is None)):
                raise ValueError("rule %r is a duplicate, has an unknown kind, or lacks a "
                                 "replacement or a version" % rule["name"])
            group[key] = rule
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("rule table %s is malformed: %r" % (path, exc))
    return table


def all_rules(table):
    rules = list(table["rules"].values()) + list(table["methods"].values())
    return sorted(rules, key=lambda r: (r["removed_in"] or r["deprecated_in"], r["name"]))


def match_rule(qualified, rules):
    """Most specific rule whose name equals the dotted name or is a dotted prefix of it."""
    parts = qualified.split(".")
    for end in range(len(parts), 0, -1):
        rule = rules.get(".".join(parts[:end]))
        if rule is not None:
            return rule
    return None


def classify(rule, target):
    if rule["removed_in"] is not None:
        return "removed" if rule["removed_in"] <= target else "later"
    return "deprecated" if rule["deprecated_in"] <= target else None


def collect_bindings(tree):
    """Map each local name to the dotted name it was imported as.

    A name is left out when the file binds it in more than one way (two
    different imports, an assignment, a parameter, a def). Uses of such a name
    are not resolved, so a local variable is never mistaken for a module.
    """
    seen = {}

    def bind(name, target):
        seen.setdefault(name, set()).add(target)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                bind(alias.asname or top, alias.name if alias.asname else top)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    relative = node.level or not node.module
                    bind(alias.asname or alias.name, None if relative else "%s.%s" % (node.module, alias.name))
        elif isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            bind(node.id, None)
        elif isinstance(node, ast.arg):
            bind(node.arg, None)
        elif type(node).__name__ in ("FunctionDef", "AsyncFunctionDef", "ClassDef", "ExceptHandler",
                                     "MatchAs", "MatchStar") and node.name:
            bind(node.name, None)
    return {name: next(iter(targets)) for name, targets in seen.items()
            if len(targets) == 1 and None not in targets}


def catches_missing_name(handler):
    if handler.type is None:
        return True
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(getattr(t, "id", getattr(t, "attr", None)) in GUARD_EXCEPTIONS for t in types)


def is_guard_test(test):
    """True for a condition that looks at the interpreter version or uses hasattr."""
    for node in ast.walk(test):
        if isinstance(node, ast.Attribute) and node.attr in ("version_info", "hexversion"):
            return True
        if isinstance(node, ast.Name) and node.id in ("version_info", "hasattr"):
            return True
    return False


def is_deprecation_filter(call, category_index):
    """True for filterwarnings/simplefilter("ignore", ...) that covers DeprecationWarning."""
    keywords = dict((kw.arg, kw.value) for kw in call.keywords if kw.arg)
    action = call.args[0] if call.args else keywords.get("action")
    if not (isinstance(action, ast.Constant) and action.value == "ignore"):
        return False
    category = call.args[category_index] if len(call.args) > category_index else keywords.get("category")
    if category is None:
        return True  # no category: every warning is ignored
    name = getattr(category, "id", getattr(category, "attr", None))
    return name in ("DeprecationWarning", "PendingDeprecationWarning", "Warning")


class Scanner(ast.NodeVisitor):
    """Collects (line, column, rule, name as used, guarded, forced status)."""

    def __init__(self, table, bindings, defined):
        self.rules = table["rules"]
        self.methods = table["methods"]
        self.bindings = bindings
        self.defined = defined
        self.guard = 0
        self.hits = []

    def hit(self, node, rule, used_as, status=None):
        self.hits.append((node.lineno, node.col_offset, rule, used_as, self.guard > 0, status))

    def check_import(self, node, qualified):
        rule = match_rule(qualified, self.rules)
        if rule is not None:
            self.hit(node, rule, qualified)

    def resolve(self, node):
        """(imported name, full dotted name) for a Name or attribute chain, else (None, None)."""
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        base = self.bindings.get(node.id) if isinstance(node, ast.Name) else None
        if base is None:
            return None, None
        return base, ".".join([base] + parts[::-1])

    def visit_block(self, nodes, guarded):
        self.guard += int(guarded)
        for node in nodes:
            self.visit(node)
        self.guard -= int(guarded)

    def visit_Import(self, node):
        for alias in node.names:
            self.check_import(node, alias.name)

    def visit_ImportFrom(self, node):
        if node.level or not node.module:
            return  # relative import: never the standard library
        for alias in node.names:
            name = node.module if alias.name == "*" else "%s.%s" % (node.module, alias.name)
            self.check_import(node, name)

    def visit_Attribute(self, node):
        base, qualified = self.resolve(node)
        if qualified is None:
            inner = node
            while isinstance(inner, ast.Attribute):
                inner = inner.value
            if not isinstance(inner, ast.Name):
                self.visit(inner)
            return
        rule = match_rule(qualified, self.rules)
        # The import line already carries the rule that matches the bare
        # import, so report a use only when it adds a more specific rule.
        if rule is not None and rule is not match_rule(base, self.rules):
            self.hit(node, rule, qualified)

    def visit_Call(self, node):
        func = node.func
        if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                and func.value.id == "self" and func.attr in self.methods
                and func.attr not in self.defined):
            self.hit(node, self.methods[func.attr], "self." + func.attr)
        dunder_import = isinstance(func, ast.Name) and func.id == "__import__"
        name = "__import__" if dunder_import else self.resolve(func)[1]
        first = node.args[0] if node.args else None
        if name in ("__import__", "importlib.import_module"):
            if isinstance(first, ast.Constant) and isinstance(first.value, str) \
                    and first.value and not first.value.startswith("."):
                self.check_import(node, first.value)
        elif name in WARNING_FILTERS and is_deprecation_filter(node, WARNING_FILTERS[name]):
            self.hit(node, SILENCED_RULE, name, "silenced")
        self.generic_visit(node)

    def visit_Try(self, node):
        flags = [catches_missing_name(handler) for handler in node.handlers]
        self.visit_block(node.body, any(flags))
        for handler, flag in zip(node.handlers, flags):
            self.visit_block(handler.body, flag)
        self.visit_block(node.orelse + node.finalbody, False)

    visit_TryStar = visit_Try

    def visit_If(self, node):
        self.visit(node.test)
        branches = node.body + node.orelse if isinstance(node, ast.If) else [node.body, node.orelse]
        self.visit_block(branches, is_guard_test(node.test))

    visit_IfExp = visit_If


def local_modules(directory, cache):
    """Names importable from a directory: x.py files and packages with __init__.py."""
    if directory not in cache:
        names = set()
        for entry in (os.listdir(directory) if os.path.isdir(directory) else []):
            if entry.endswith(".py"):
                names.add(entry[:-3])
            elif os.path.isfile(os.path.join(directory, entry, "__init__.py")):
                names.add(entry)
        cache[directory] = names
    return cache[directory]


def scan_file(path, shown, table, target, local_names):
    """Return (findings, parse error or None) for one file."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
        tree = ast.parse(data, filename=shown)
    except (SyntaxError, ValueError, RecursionError, OSError) as exc:
        return [], {"path": shown, "line": getattr(exc, "lineno", None) or 0,
                    "message": getattr(exc, "msg", None) or str(exc)}
    lines = data.decode("utf-8", errors="replace").splitlines()
    defined = set(node.name for node in ast.walk(tree)
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    scanner = Scanner(table, collect_bindings(tree), defined)
    scanner.visit(tree)
    findings, seen = [], set()
    for line, col, rule, used_as, guarded, forced in sorted(scanner.hits, key=lambda h: h[:2] + (h[2]["name"],)):
        status = forced or classify(rule, target)
        if status is None or (line, rule["name"]) in seen:
            continue
        seen.add((line, rule["name"]))
        if rule["kind"] in ("module", "api") and used_as.split(".")[0] in local_names:
            status = "shadowed"
        elif guarded:
            status = "guarded"
        version = rule["removed_in"] or rule["deprecated_in"]
        findings.append({
            "path": shown, "line": line, "col": col, "status": status,
            "rule": rule["name"], "kind": rule["kind"], "used_as": used_as,
            "removed_in": show_version(rule["removed_in"]),
            "deprecated_in": show_version(rule["deprecated_in"]),
            "replacement": rule["replacement"],
            "source": lines[line - 1].strip()[:140] if 0 < line <= len(lines) else "",
            "docs": WHATS_NEW % show_version(version) if version else None,
        })
    return findings, None


def find_files(paths, excludes):
    """Yield (real path, shown path, scan root) for each .py file, in sorted order."""
    def excluded(rel):
        return any(fnmatch.fnmatch(rel, pattern) for pattern in excludes)

    def shown(path):
        return os.path.normpath(path).replace(os.sep, "/")

    for given in paths:
        if os.path.isfile(given):
            yield given, shown(given), os.path.dirname(os.path.abspath(given))
        elif os.path.isdir(given):
            for folder, dirs, files in os.walk(given):
                rel_folder = os.path.relpath(folder, given).replace(os.sep, "/")
                prefix = "" if rel_folder == "." else rel_folder + "/"
                dirs[:] = sorted(
                    d for d in dirs
                    if not d.startswith(".") and d not in SKIP_DIRS and not excluded(prefix + d)
                    and not os.path.isfile(os.path.join(folder, d, "pyvenv.cfg")))
                for name in sorted(files):
                    if name.endswith(".py") and not excluded(prefix + name):
                        yield os.path.join(folder, name), shown(os.path.join(folder, name)), os.path.abspath(given)
        else:
            raise ValueError("no such file or directory: %s" % given)


def scan(paths, target, table, excludes=(), fail_on="removed"):
    cache, done = {}, set()
    findings, parse_errors, count = [], [], 0
    for path, shown, root in find_files(paths, excludes):
        if os.path.abspath(path) in done:
            continue  # the same file reached through two of the given paths
        done.add(os.path.abspath(path))
        count += 1
        local_names = set()
        for folder in (os.path.dirname(os.path.abspath(path)), root, os.path.join(root, "src")):
            local_names |= local_modules(folder, cache)
        found, error = scan_file(path, shown, table, target, local_names)
        findings.extend(found)
        if error:
            parse_errors.append(error)
    findings.sort(key=lambda f: (f["path"], f["line"], f["col"], f["rule"]))
    summary = dict((status, 0) for status in ("removed",) + WARNING_STATUSES + ("guarded", "shadowed"))
    for finding in findings:
        summary[finding["status"]] += 1
    blocking = summary["removed"]
    if fail_on == "warning":
        blocking += sum(summary[status] for status in WARNING_STATUSES)
    return {
        "target": show_version(target),
        "fail_on": fail_on,
        "rule_table": {"rules": len(all_rules(table)), "first_version": show_version(table["first"]),
                       "last_version": show_version(table["last"]),
                       "target_beyond_table": target > table["last"]},
        "files_scanned": count,
        "summary": summary,
        "blocking": blocking,
        "findings": findings,
        "parse_errors": parse_errors,
    }


def when(finding):
    fixed = {"shadowed": "local module of the same name", "silenced": "ignores DeprecationWarning"}
    if finding["status"] in fixed:
        return fixed[finding["status"]]
    if finding["removed_in"]:
        return "removed in %s" % finding["removed_in"]
    return "deprecated since %s" % finding["deprecated_in"]


def render_text(result):
    target, table = result["target"], result["rule_table"]
    out = ["compat_scan: target Python %s, %d file(s) scanned, %d rules for Python %s to %s" % (
        target, result["files_scanned"], table["rules"], table["first_version"], table["last_version"])]
    groups = [
        ("BREAKS on Python %s" % target, ("removed",)),
        ("Works on Python %s, breaks later or is deprecated" % target, WARNING_STATUSES),
        ("Guarded by try/except or a version check: confirm the fallback path", ("guarded",)),
        ("Not counted: the import resolves to a module in this project", ("shadowed",)),
    ]
    for title, statuses in groups:
        rows = [f for f in result["findings"] if f["status"] in statuses]
        if not rows:
            continue
        out.extend(["", "%s (%d)" % (title, len(rows))])
        for f in rows:
            out.append("  %s:%d  %s  [%s]" % (f["path"], f["line"], f["rule"], when(f)))
            out.append("      %s" % f["source"])
            if f["status"] != "shadowed":
                out.append("      fix: %s" % f["replacement"])
    if result["parse_errors"]:
        out.extend(["", "NOT SCANNED: this interpreter (Python %d.%d) could not parse (%d)" % (
            sys.version_info[0], sys.version_info[1], len(result["parse_errors"]))])
        for error in result["parse_errors"]:
            out.append("  %s:%d  %s" % (error["path"], error["line"], error["message"]))
    out.append("")
    if table["target_beyond_table"]:
        out.append("NOTE: the rule table stops at Python %s. Removals in later versions are not "
                   "checked; read the What's New pages for them." % table["last_version"])
    if result["parse_errors"]:
        out.append("RESULT: %d blocking finding(s) for Python %s, and %d file(s) not scanned." % (
            result["blocking"], target, len(result["parse_errors"])))
    elif result["blocking"]:
        out.append("RESULT: %d blocking finding(s) for Python %s. Each version's changes: %s" % (
            result["blocking"], target, WHATS_NEW % "<version>"))
    else:
        out.append("RESULT: nothing blocking for Python %s. The table is not exhaustive: the proof is "
                   "the test suite passing on Python %s with -W error::DeprecationWarning." % (target, target))
    return "\n".join(out)


def render_rules(table):
    return "\n".join(
        "%-18s %-7s %s  ->  %s" % (
            "removed in %s" % show_version(rule["removed_in"]) if rule["removed_in"]
            else "deprecated in %s" % show_version(rule["deprecated_in"]),
            rule["kind"], rule["name"], rule["replacement"])
        for rule in all_rules(table))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="files or directories to scan")
    parser.add_argument("--target", help="Python version being upgraded to, for example 3.12")
    parser.add_argument("--fail-on", choices=("removed", "warning"), default="removed",
                        help="removed (default): only names gone at the target block. "
                             "warning: later, deprecated and silenced findings block too")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="skip paths matching this glob, relative to each scanned directory; repeatable")
    parser.add_argument("--rules", default=RULES_FILE, help="rule table to use (default: compat_rules.json)")
    parser.add_argument("--list-rules", action="store_true", help="print the rule table and exit")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)

    try:
        table = load_rules(args.rules)
        if args.list_rules:
            print(render_rules(table))
            return 0
        if not args.target:
            parser.error("--target is required, for example --target 3.12")
        if not args.paths:
            parser.error("give at least one file or directory to scan")
        target = parse_version(args.target)
        if target < table["first"]:
            raise ValueError("the rule table starts at Python %s; a target of %s is not supported"
                             % (show_version(table["first"]), show_version(target)))
        result = scan(args.paths, target, table, args.exclude, args.fail_on)
    except ValueError as exc:
        print("compat_scan.py: error: %s" % exc, file=sys.stderr)
        return 2
    if result["files_scanned"] == 0:
        print("compat_scan.py: error: no .py files found in %s" % ", ".join(args.paths), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render_text(result))
    return 1 if result["blocking"] or result["parse_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
