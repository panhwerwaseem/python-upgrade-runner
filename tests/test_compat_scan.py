import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "python-upgrade-runner"
FIXTURES = SKILL / "evals" / "files"
sys.path.insert(0, str(SKILL / "scripts"))

import compat_scan  # noqa: E402

TABLE = compat_scan.load_rules(compat_scan.RULES_FILE)


def run_main(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = compat_scan.main(list(argv))
        except SystemExit as exc:  # argparse usage errors
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def scan_fixture(name, target, *extra):
    """Scan a fixture project; return (exit code, {status: {(relative path, line, rule)}})."""
    folder = FIXTURES / name
    code, out, _ = run_main("--target", target, "--json", str(folder), *extra)
    by_status = {}
    for finding in json.loads(out)["findings"]:
        rel = os.path.relpath(finding["path"], str(folder)).replace(os.sep, "/")
        by_status.setdefault(finding["status"], set()).add((rel, finding["line"], finding["rule"]))
    return code, by_status


class TempProject(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, rel, source):
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return path

    def scan(self, target="3.13", **kwargs):
        return compat_scan.scan([str(self.dir)], compat_scan.parse_version(target), TABLE, **kwargs)

    def found(self, target="3.13", **kwargs):
        """[(status, rule, line)] for the temp project."""
        return [(f["status"], f["rule"], f["line"]) for f in self.scan(target, **kwargs)["findings"]]


class RuleTableTests(unittest.TestCase):
    def test_bundled_table_loads_and_every_rule_is_complete(self):
        rules = compat_scan.all_rules(TABLE)
        self.assertGreater(len(rules), 100)
        for rule in rules:
            self.assertIn(rule["kind"], ("module", "api", "method"))
            self.assertTrue(rule["removed_in"] or rule["deprecated_in"], rule["name"])
            self.assertTrue(rule["replacement"].strip(), rule["name"])
            version = rule["removed_in"] or rule["deprecated_in"]
            self.assertTrue(TABLE["first"] <= version <= TABLE["last"], rule["name"])

    def test_versions_named_in_the_skill_spec(self):
        expected = {"distutils": (3, 12), "imp": (3, 12), "asyncore": (3, 12), "asynchat": (3, 12),
                    "smtpd": (3, 12), "cgi": (3, 13), "telnetlib": (3, 13), "pipes": (3, 13),
                    "collections.Mapping": (3, 10)}
        for name, version in expected.items():
            self.assertEqual(TABLE["rules"][name]["removed_in"], version, name)

    def test_all_nineteen_pep_594_modules_removed_in_3_13_are_listed(self):
        names = ("aifc audioop cgi cgitb chunk crypt imghdr mailcap msilib nis nntplib ossaudiodev "
                 "pipes sndhdr spwd sunau telnetlib uu xdrlib").split()
        self.assertEqual(len(names), 19)
        for name in names:
            self.assertEqual(TABLE["rules"][name]["removed_in"], (3, 13), name)
            self.assertEqual(TABLE["rules"][name]["kind"], "module")

    def test_every_rule_is_documented_in_the_breaking_changes_reference(self):
        text = (SKILL / "references" / "breaking-changes.md").read_text(encoding="utf-8")
        for rule in compat_scan.all_rules(TABLE):
            short = rule["name"].rsplit(".", 1)[-1]
            self.assertIn("`%s`" % short if rule["kind"] == "method" or rule["name"].startswith("collections.")
                          else "`%s`" % rule["name"], text, rule["name"])

    def test_most_specific_rule_wins(self):
        rules = TABLE["rules"]
        self.assertEqual(compat_scan.match_rule("distutils.util.strtobool", rules)["name"],
                         "distutils.util.strtobool")
        self.assertEqual(compat_scan.match_rule("distutils.command.build_ext", rules)["name"], "distutils")
        self.assertIsNone(compat_scan.match_rule("importlib.util", rules))  # "imp" is not a prefix
        self.assertIsNone(compat_scan.match_rule("collections.abc.Mapping", rules))
        self.assertIsNone(compat_scan.match_rule("email.parser", rules))

    def test_classify_by_target(self):
        rules = TABLE["rules"]
        self.assertEqual(compat_scan.classify(rules["imp"], (3, 12)), "removed")
        self.assertEqual(compat_scan.classify(rules["imp"], (3, 11)), "later")
        self.assertEqual(compat_scan.classify(rules["datetime.datetime.utcnow"], (3, 12)), "deprecated")
        self.assertIsNone(compat_scan.classify(rules["datetime.datetime.utcnow"], (3, 11)))

    def test_parse_version(self):
        self.assertEqual(compat_scan.parse_version("3.12"), (3, 12))
        self.assertEqual(compat_scan.parse_version("3.12.4"), (3, 12))
        for bad in ("3", "312", "three.twelve", "", "3.x"):
            with self.assertRaises(ValueError):
                compat_scan.parse_version(bad)

    def test_bad_rule_tables_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rules.json"
            cases = [
                "{not json",
                json.dumps({"rules": []}),
                json.dumps({"covers": {"first": "3.8", "last": "3.14"},
                            "rules": [{"name": "x", "kind": "module", "replacement": "y"}]}),
                json.dumps({"covers": {"first": "3.8", "last": "3.14"},
                            "rules": [{"name": "x", "kind": "weird", "removed_in": "3.9", "replacement": "y"}]}),
            ]
            for text in cases:
                path.write_text(text)
                with self.assertRaises(ValueError):
                    compat_scan.load_rules(str(path))
                self.assertEqual(run_main("--rules", str(path), "--target", "3.12", folder)[0], 2)


class FixtureTests(unittest.TestCase):
    def test_legacy_app_planted_removals_for_3_12(self):
        code, found = scan_fixture("legacy-app", "3.12")
        self.assertEqual(code, 1)
        self.assertEqual(found["removed"], {
            ("setup.py", 1, "distutils.core"),
            ("inventory/config.py", 2, "collections.Mapping"),
            ("inventory/config.py", 3, "configparser.SafeConfigParser"),
            ("inventory/plugins.py", 2, "imp"),
            ("inventory/plugins.py", 8, "imp.load_source"),
            ("inventory/report.py", 11, "inspect.getargspec"),
            ("tests/test_config.py", 18, "unittest.TestCase.assertEquals"),
            ("tests/test_config.py", 22, "unittest.TestCase.assertEquals"),
        })
        self.assertEqual(found["deprecated"], {("inventory/report.py", 7, "datetime.datetime.utcnow")})
        self.assertEqual(found["guarded"], {("inventory/compat.py", 5, "collections.Callable")})
        self.assertEqual(set(found), {"removed", "deprecated", "guarded"})

    def test_legacy_app_at_3_10_blocks_only_on_what_3_10_removed(self):
        code, found = scan_fixture("legacy-app", "3.10")
        self.assertEqual(code, 1)
        self.assertEqual(found["removed"], {("inventory/config.py", 2, "collections.Mapping")})
        self.assertEqual(len(found["later"]), 7)
        self.assertNotIn("deprecated", found)  # utcnow is not deprecated before 3.12

    def test_mail_gateway_planted_removals_for_3_13(self):
        code, found = scan_fixture("mail-gateway", "3.13")
        self.assertEqual(code, 1)
        self.assertEqual(found["removed"], {
            ("gateway/inbound.py", 2, "asyncore"),
            ("gateway/inbound.py", 3, "smtpd"),
            ("gateway/shell.py", 2, "pipes"),
            ("gateway/shell.py", 6, "pipes.quote"),
            ("gateway/uploads.py", 2, "cgi"),
            ("gateway/uploads.py", 3, "imghdr"),
        })
        self.assertEqual(found["silenced"], {("gateway/__init__.py", 4, "warnings-filter")})
        self.assertEqual(found["guarded"], {("gateway/probe.py", 5, "telnetlib")})

    def test_mail_gateway_at_3_12_separates_now_from_later(self):
        code, found = scan_fixture("mail-gateway", "3.12")
        self.assertEqual(code, 1)
        self.assertEqual(found["removed"], {("gateway/inbound.py", 2, "asyncore"),
                                            ("gateway/inbound.py", 3, "smtpd")})
        self.assertEqual({rule for _, _, rule in found["later"]}, {"pipes", "pipes.quote", "cgi", "imghdr"})

    def test_mid_upgrade_finds_the_cause_of_the_failing_stage(self):
        code, found = scan_fixture("mid-upgrade", "3.11")
        self.assertEqual(code, 1)
        self.assertEqual(found["removed"], {("billing/signature.py", 6, "inspect.getargspec")})
        code, found = scan_fixture("mid-upgrade", "3.10")
        self.assertEqual(code, 0)
        self.assertEqual(found, {"later": {("billing/signature.py", 6, "inspect.getargspec")}})

    def test_clean_app_has_no_finding_at_any_supported_target(self):
        for minor in range(8, 15):
            target = "3.%d" % minor
            for extra in ((), ("--fail-on", "warning")):
                code, found = scan_fixture("clean-app", target, *extra)
                self.assertEqual(code, 0, target)
                # The only entry is the note that "import parser" is the project's own parser.py.
                self.assertEqual(found, {"shadowed": {("cli.py", 4, "parser")}}, target)

    def test_text_report_names_file_line_version_and_fix(self):
        code, out, _ = run_main("--target", "3.12", str(FIXTURES / "legacy-app"))
        self.assertEqual(code, 1)
        self.assertIn("BREAKS on Python 3.12 (8)", out)
        self.assertIn("inventory/plugins.py:2  imp  [removed in 3.12]", out)
        self.assertIn("fix: importlib", out)
        self.assertIn("RESULT: 8 blocking finding(s) for Python 3.12", out)

    def test_output_is_deterministic(self):
        first = run_main("--target", "3.13", "--json", str(FIXTURES / "mail-gateway"))
        second = run_main("--target", "3.13", "--json", str(FIXTURES / "mail-gateway"))
        self.assertEqual(first, second)


class DetectionTests(TempProject):
    def test_import_forms(self):
        self.write("a.py", """\
            import imp
            import distutils.util
            import asyncore as loop
            from pipes import quote
            from distutils.util import strtobool, get_platform
            from telnetlib import *
            """)
        self.assertEqual(self.found(), [
            ("removed", "imp", 1), ("removed", "distutils", 2), ("removed", "asyncore", 3),
            ("removed", "pipes.quote", 4), ("removed", "distutils.util.get_platform", 5),
            ("removed", "distutils.util.strtobool", 5), ("removed", "telnetlib", 6)])

    def test_attribute_use_through_plain_and_aliased_imports(self):
        self.write("a.py", """\
            import collections
            import collections as c
            import datetime as dt
            from datetime import datetime
            import unittest, inspect, ssl

            def f(value, sock):
                isinstance(value, collections.Mapping)
                isinstance(value, c.MutableSet)
                dt.datetime.utcnow()
                datetime.utcfromtimestamp(0)
                unittest.makeSuite(object)
                inspect.getargspec(f).args
                ssl.wrap_socket(sock)
            """)
        self.assertEqual(self.found(), [
            ("removed", "collections.Mapping", 8), ("removed", "collections.MutableSet", 9),
            ("deprecated", "datetime.datetime.utcnow", 10),
            ("deprecated", "datetime.datetime.utcfromtimestamp", 11),
            ("removed", "unittest.makeSuite", 12), ("removed", "inspect.getargspec", 13),
            ("removed", "ssl.wrap_socket", 14)])

    def test_use_of_removed_module_is_reported_once_at_the_import(self):
        self.write("a.py", """\
            import cgi
            from collections import Mapping
            cgi.parse_header("text/plain")
            cgi.FieldStorage()
            Mapping.register(dict)
            """)
        self.assertEqual(self.found(), [("removed", "cgi", 1), ("removed", "collections.Mapping", 2)])

    def test_a_use_adds_a_finding_only_when_a_more_specific_rule_applies(self):
        self.write("a.py", """\
            import distutils.util
            import cgi
            flag = distutils.util.strtobool("yes")
            text = cgi.escape("<b>")
            """)
        self.assertEqual(self.found(), [
            ("removed", "distutils", 1), ("removed", "cgi", 2),
            ("removed", "distutils.util.strtobool", 3), ("removed", "cgi.escape", 4)])

    def test_decorator_and_dynamic_imports(self):
        self.write("a.py", """\
            import asyncio
            import importlib
            from importlib import import_module

            @asyncio.coroutine
            def old():
                yield

            a = importlib.import_module("imghdr")
            b = import_module("xdrlib")
            c = __import__("nntplib")
            d = importlib.import_module(".sibling", __package__)
            e = importlib.import_module(name)
            """)
        self.assertEqual(self.found(), [
            ("removed", "asyncio.coroutine", 5), ("removed", "imghdr", 9),
            ("removed", "xdrlib", 10), ("removed", "nntplib", 11)])

    def test_unittest_aliases_on_self(self):
        self.write("test_a.py", """\
            import unittest

            class T(unittest.TestCase):
                def test_it(self):
                    self.assertEquals(1, 1)
                    self.assert_(True)
                    self.failUnless(True)
                    self.assertRaisesRegexp(ValueError, "x", int, "x")
                    self.assertEqual(1, 1)
                    other.assertEquals(1, 1)
            """)
        self.assertEqual(self.found("3.12"), [
            ("removed", "unittest.TestCase.assertEquals", 5), ("removed", "unittest.TestCase.assert_", 6),
            ("removed", "unittest.TestCase.failUnless", 7),
            ("removed", "unittest.TestCase.assertRaisesRegexp", 8)])
        self.assertEqual({status for status, _, _ in self.found("3.11")}, {"later"})

    def test_alias_defined_in_the_same_file_is_not_flagged(self):
        self.write("a.py", """\
            class Checker:
                def assertEquals(self, a, b):
                    return a == b
                def run(self):
                    return self.assertEquals(1, 1)
            """)
        self.assertEqual(self.found(), [])

    def test_names_that_only_look_like_removed_modules_are_ignored(self):
        self.write("pkg/__init__.py", "")
        self.write("pkg/a.py", """\
            # import imp, distutils
            from . import imp, formatter
            from .parser import parse
            from email import parser as email_parser
            from collections.abc import Mapping
            import collections

            def render(cgi, pipes):
                parser = email_parser.Parser()
                telnetlib = "import telnetlib"
                asyncore = {}
                imp.reload(formatter)
                return cgi.escape(pipes.quote(asyncore.get(telnetlib))), parser, parse, Mapping

            class Clock:
                def utcnow(self):
                    return collections.OrderedDict()
            now = Clock().utcnow()
            """)
        self.assertEqual(self.found("3.14"), [])

    def test_rebound_import_name_is_not_resolved(self):
        self.write("a.py", """\
            import datetime
            from datetime import datetime
            datetime.utcnow()
            """)
        self.assertEqual(self.found(), [])

    def test_guards_downgrade_to_review(self):
        self.write("a.py", """\
            import sys
            try:
                import imp
            except ImportError:
                imp = None
            try:
                from shlex import quote
            except (ImportError, AttributeError):
                from pipes import quote
            if sys.version_info < (3, 12):
                import asyncore
            else:
                asyncore = None
            import inspect
            argspec = inspect.getfullargspec if hasattr(inspect, "getfullargspec") else inspect.getargspec
            try:
                import smtpd
            except ValueError:
                pass
            try:
                pass
            finally:
                import uu
            """)
        result = self.scan()
        self.assertEqual([(f["status"], f["rule"], f["line"]) for f in result["findings"]], [
            ("guarded", "imp", 3), ("guarded", "pipes.quote", 9), ("guarded", "asyncore", 11),
            ("guarded", "inspect.getargspec", 15), ("removed", "smtpd", 17), ("removed", "uu", 23)])
        self.assertEqual(result["blocking"], 2)

    def test_warning_filters_that_hide_deprecations(self):
        self.write("a.py", """\
            import warnings
            from warnings import simplefilter
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            warnings.filterwarnings("ignore", "", PendingDeprecationWarning, "pkg")
            warnings.simplefilter("ignore")
            simplefilter(action="ignore", category=Warning)
            warnings.filterwarnings("error", category=DeprecationWarning)
            warnings.filterwarnings("ignore", category=ResourceWarning)
            warnings.simplefilter("default", DeprecationWarning)
            """)
        self.assertEqual(self.found(), [("silenced", "warnings-filter", line) for line in (3, 4, 5, 6)])
        self.assertEqual(self.scan()["blocking"], 0)
        self.assertEqual(self.scan(fail_on="warning")["blocking"], 4)

    def test_local_module_shadows_the_standard_library_name(self):
        self.write("parser.py", "def parse(text):\n    return text\n")
        self.write("main.py", "import parser\nimport formatter\nparser.parse('x')\n")
        self.write("src/imp/__init__.py", "")
        self.write("tools/build.py", "import imp\nimport parser\n")
        self.assertEqual(self.found(), [
            ("shadowed", "parser", 1), ("removed", "formatter", 2),
            ("shadowed", "imp", 1), ("shadowed", "parser", 2)])
        self.assertEqual(self.scan()["blocking"], 1)

    def test_fail_on_warning_blocks_on_later_and_deprecated(self):
        self.write("a.py", "import cgi\nimport datetime\ndatetime.datetime.utcnow()\n")
        self.assertEqual(self.scan("3.12")["blocking"], 0)
        self.assertEqual(self.scan("3.12", fail_on="warning")["blocking"], 2)
        code, _, _ = run_main("--target", "3.12", "--fail-on", "warning", str(self.dir))
        self.assertEqual(code, 1)

    def test_finding_carries_evidence(self):
        self.write("a.py", "import os\nimport imp  # legacy loader\n")
        finding = self.scan()["findings"][0]
        self.assertTrue(finding["path"].endswith("a.py"))
        self.assertEqual((finding["line"], finding["col"]), (2, 0))
        self.assertEqual(finding["source"], "import imp  # legacy loader")
        self.assertEqual(finding["removed_in"], "3.12")
        self.assertEqual(finding["replacement"], "importlib")
        self.assertEqual(finding["docs"], "https://docs.python.org/3/whatsnew/3.12.html")


class FilesAndErrorsTests(TempProject):
    def test_virtualenvs_hidden_and_vendored_folders_are_skipped(self):
        self.write("app.py", "import os\n")
        self.write("env39/pyvenv.cfg", "home = /usr/bin\n")
        self.write("env39/lib/python3.9/site-packages/old.py", "import imp\n")
        self.write(".tox/py39/x.py", "import imp\n")
        self.write("node_modules/gyp/x.py", "import imp\n")
        self.write("vendor/six.py", "import imp\n")
        result = self.scan()
        self.assertEqual((result["files_scanned"], result["blocking"]), (2, 1))
        result = self.scan(excludes=["vendor/*"])
        self.assertEqual((result["files_scanned"], result["blocking"]), (1, 0))
        self.assertEqual(self.scan(excludes=["vendor"])["files_scanned"], 1)

    def test_overlapping_paths_do_not_duplicate_findings(self):
        self.write("pkg/a.py", "import imp\n")
        target = compat_scan.parse_version("3.12")
        result = compat_scan.scan([str(self.dir), str(self.dir / "pkg"), str(self.dir / "pkg" / "a.py")],
                                  target, TABLE)
        self.assertEqual((result["files_scanned"], result["blocking"]), (1, 1))

    def test_empty_bom_and_undecodable_files(self):
        self.write("empty.py", "")
        (self.dir / "bom.py").write_bytes(b"\xef\xbb\xbfimport imp\n")
        (self.dir / "binary.py").write_bytes(b"name = '\xff\xfe'\n")
        result = self.scan()
        self.assertEqual([(f["path"].rsplit("/", 1)[-1], f["rule"]) for f in result["findings"]],
                         [("bom.py", "imp")])
        self.assertEqual([e["path"].rsplit("/", 1)[-1] for e in result["parse_errors"]], ["binary.py"])

    def test_unparsable_file_is_reported_and_blocks(self):
        self.write("ok.py", "import os\n")
        self.write("py2.py", "print 'hello'\nimport imp\n")
        result = self.scan()
        self.assertEqual(result["findings"], [])
        self.assertEqual(len(result["parse_errors"]), 1)
        self.assertEqual(result["parse_errors"][0]["line"], 1)
        code, out, _ = run_main("--target", "3.12", str(self.dir))
        self.assertEqual(code, 1)
        self.assertIn("NOT SCANNED", out)
        self.assertIn("py2.py:1", out)
        self.assertIn("1 file(s) not scanned", out)

    def test_single_file_argument_and_encoding_declaration(self):
        path = self.dir / "latin.py"
        path.write_bytes(b"# -*- coding: latin-1 -*-\nname = '\xe9'\nimport imp\n")
        code, out, _ = run_main("--target", "3.12", "--json", str(path))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["findings"][0]["line"], 3)

    def test_target_beyond_the_table_is_flagged(self):
        self.write("a.py", "import os\n")
        code, out, _ = run_main("--target", "3.99", str(self.dir))
        self.assertEqual(code, 0)
        self.assertIn("rule table stops at Python 3.14", out)
        self.assertTrue(self.scan("3.99")["rule_table"]["target_beyond_table"])
        self.assertFalse(self.scan("3.14")["rule_table"]["target_beyond_table"])

    def test_clean_result_says_the_scan_is_not_proof(self):
        self.write("a.py", "import os\n")
        code, out, _ = run_main("--target", "3.13", str(self.dir))
        self.assertEqual(code, 0)
        self.assertIn("nothing blocking for Python 3.13", out)
        self.assertIn("not exhaustive", out)

    def test_usage_and_input_errors_exit_2(self):
        self.write("a.py", "import os\n")
        empty = self.dir / "empty"
        empty.mkdir()
        cases = [
            (str(self.dir),),                                   # no --target
            ("--target", "3.12"),                               # no path
            ("--target", "three", str(self.dir)),               # bad version
            ("--target", "3.7", str(self.dir)),                 # before the table
            ("--target", "3.12", str(self.dir / "missing")),    # no such path
            ("--target", "3.12", str(empty)),                   # nothing to scan
            ("--target", "3.12", "--fail-on", "x", str(self.dir)),
        ]
        for argv in cases:
            code, out, err = run_main(*argv)
            self.assertEqual(code, 2, argv)
            self.assertNotIn("Traceback", err)

    def test_list_rules_prints_the_table(self):
        code, out, _ = run_main("--list-rules")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), len(compat_scan.all_rules(TABLE)))
        self.assertIn("removed in 3.12    module  distutils  ->", out)

    def test_help_has_examples_and_exit_codes(self):
        code, out, _ = run_main("--help")
        self.assertEqual(code, 0)
        self.assertIn("Examples:", out)
        self.assertIn("Exit codes:", out)


class ValidateRepoTests(unittest.TestCase):
    def test_repository_passes_its_own_validator(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import validate
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = validate.main(["validate.py", str(ROOT)])
        self.assertEqual(code, 0, buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
