import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "python-upgrade-runner"
sys.path.insert(0, str(SKILL / "scripts"))

import stage_ledger  # noqa: E402

PASS = [sys.executable, "-c", "print('ran 12 tests, OK')"]
FAIL = [sys.executable, "-c", "import sys; print('E   ModuleNotFoundError: imp'); sys.exit(1)"]


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "work" / "ledger.json"

    def run_cli(self, *argv):
        """Run the CLI with --ledger set; return (exit code, stdout, stderr)."""
        argv = list(argv)
        argv[1:1] = ["--ledger", str(self.path)]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = stage_ledger.main(argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def verify(self, command):
        return self.run_cli("verify", "--", *command)

    def stages(self):
        return json.loads(self.path.read_text())["stages"]

    def passing_baseline(self, python="3.9"):
        self.assertEqual(self.run_cli("open", "baseline", "--python", python)[0], 0)
        self.assertEqual(self.verify(PASS)[0], 0)


class OpenTests(LedgerCase):
    def test_first_stage_must_be_the_baseline(self):
        code, out, _ = self.run_cli("open", "python 3.12", "--python", "3.12")
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("baseline", out)
        self.assertFalse(self.path.exists())

    def test_baseline_opens_and_creates_the_ledger(self):
        code, out, _ = self.run_cli("open", "Baseline", "--python", "3.9", "--note", "as deployed")
        self.assertEqual(code, 0)
        stage = self.stages()[0]
        self.assertEqual((stage["id"], stage["name"], stage["python"], stage["note"]),
                         (1, "Baseline", "3.9", "as deployed"))
        self.assertEqual(stage["verifications"], [])

    def test_refuses_next_stage_while_current_is_unverified(self):
        self.run_cli("open", "baseline")
        code, out, _ = self.run_cli("open", "tooling")
        self.assertEqual(code, 1)
        self.assertIn("has not been verified", out)
        self.assertEqual(len(self.stages()), 1)

    def test_refuses_next_stage_while_current_is_failing(self):
        self.run_cli("open", "baseline")
        self.assertEqual(self.verify(FAIL)[0], 1)
        code, out, _ = self.run_cli("open", "tooling")
        self.assertEqual(code, 1)
        self.assertIn("is failing", out)
        self.assertEqual(len(self.stages()), 1)

    def test_opens_next_stage_after_a_failure_is_fixed(self):
        self.run_cli("open", "baseline")
        self.verify(FAIL)
        self.assertEqual(self.verify(PASS)[0], 0)
        self.assertEqual(self.run_cli("open", "tooling")[0], 0)
        stages = self.stages()
        self.assertEqual([s["name"] for s in stages], ["baseline", "tooling"])
        self.assertEqual([v["passed"] for v in stages[0]["verifications"]], [False, True])

    def test_a_later_failure_blocks_again(self):
        self.passing_baseline()
        self.assertEqual(self.verify(FAIL)[0], 1)
        self.assertEqual(self.run_cli("open", "tooling")[0], 1)

    def test_one_minor_version_at_a_time(self):
        self.passing_baseline("3.9")
        code, out, _ = self.run_cli("open", "python 3.12", "--python", "3.12")
        self.assertEqual(code, 1)
        self.assertIn("skips versions after 3.9", out)
        self.assertEqual(self.run_cli("open", "python 3.10", "--python", "3.10")[0], 0)
        self.verify(PASS)
        # A stage without --python (for example a dependency bump) does not reset the version.
        self.assertEqual(self.run_cli("open", "bump requests")[0], 0)
        self.verify(PASS)
        self.assertEqual(self.run_cli("open", "python 3.12", "--python", "3.12")[0], 1)
        self.assertEqual(self.run_cli("open", "same again", "--python", "3.10")[0], 0)

    def test_skip_needs_a_recorded_reason_and_downgrade_is_refused(self):
        self.passing_baseline("3.10")
        code, out, _ = self.run_cli("open", "back", "--python", "3.9")
        self.assertEqual(code, 1)
        self.assertIn("older than", out)
        code, _, _ = self.run_cli("open", "python 3.12", "--python", "3.12",
                                  "--skip-reason", "3.11 is not available on the build image")
        self.assertEqual(code, 0)
        self.assertEqual(self.stages()[-1]["skip_reason"], "3.11 is not available on the build image")
        self.verify(PASS)
        _, out, _ = self.run_cli("show")
        self.assertIn("skipped versions: 3.11 is not available", out)

    def test_bad_python_version_is_a_usage_error(self):
        code, _, err = self.run_cli("open", "baseline", "--python", "three")
        self.assertEqual(code, 2)
        self.assertIn("--python", err)


class VerifyTests(LedgerCase):
    def test_passing_command_is_recorded(self):
        self.run_cli("open", "baseline")
        code, out, _ = self.verify(PASS)
        self.assertEqual(code, 0)
        self.assertIn("stage 1 'baseline': PASSED (exit code 0, attempt 1)", out)
        attempt = self.stages()[0]["verifications"][0]
        self.assertEqual(attempt["command"], PASS)
        self.assertEqual((attempt["exit_code"], attempt["passed"]), (0, True))
        self.assertEqual(attempt["output_tail"], ["ran 12 tests, OK"])
        self.assertRegex(attempt["at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_failing_command_is_recorded_with_its_output(self):
        self.run_cli("open", "baseline")
        code, out, _ = self.verify(FAIL)
        self.assertEqual(code, 1)
        self.assertIn("FAILED (exit code 1, attempt 1)", out)
        self.assertIn("ModuleNotFoundError: imp", out)
        attempt = self.stages()[0]["verifications"][0]
        self.assertEqual((attempt["exit_code"], attempt["passed"]), (1, False))
        self.assertEqual(attempt["output_tail"], ["E   ModuleNotFoundError: imp"])

    def test_only_the_tail_of_long_output_is_kept(self):
        self.run_cli("open", "baseline")
        self.verify([sys.executable, "-c", "print('\\n'.join('line %d' % i for i in range(100)))"])
        tail = self.stages()[0]["verifications"][0]["output_tail"]
        self.assertEqual(len(tail), stage_ledger.TAIL_LINES)
        self.assertEqual(tail[-1], "line 99")

    def test_timeout_counts_as_a_failure(self):
        self.run_cli("open", "baseline")
        code, out, _ = self.run_cli("verify", "--timeout", "0.5", "--",
                                    sys.executable, "-c", "import time; time.sleep(10)")
        self.assertEqual(code, 1)
        attempt = self.stages()[0]["verifications"][0]
        self.assertEqual((attempt["exit_code"], attempt["passed"]), (None, False))
        self.assertIn("exceeded --timeout", attempt["output_tail"][-1])

    def test_command_that_cannot_start_is_an_error_and_is_not_recorded(self):
        self.run_cli("open", "baseline")
        code, _, err = self.verify(["no-such-binary-xyz"])
        self.assertEqual(code, 2)
        self.assertIn("cannot run", err)
        self.assertEqual(self.stages()[0]["verifications"], [])

    def test_verify_needs_a_ledger_and_a_command(self):
        self.assertEqual(self.verify(PASS)[0], 2)
        self.run_cli("open", "baseline")
        self.assertEqual(self.run_cli("verify")[0], 2)
        self.assertEqual(self.run_cli("verify", "--")[0], 2)

    def test_options_after_the_separator_belong_to_the_command(self):
        self.run_cli("open", "baseline")
        code, _, _ = self.verify([sys.executable, "-W", "error::DeprecationWarning", "-c", "pass"])
        self.assertEqual(code, 0)
        self.assertEqual(self.stages()[0]["verifications"][0]["command"][1:3],
                         ["-W", "error::DeprecationWarning"])


class ShowTests(LedgerCase):
    def test_show_without_a_ledger_is_an_error(self):
        code, _, err = self.run_cli("show")
        self.assertEqual(code, 2)
        self.assertIn("no ledger", err)

    def test_show_exit_code_follows_the_current_stage(self):
        self.run_cli("open", "baseline", "--python", "3.9")
        code, out, _ = self.run_cli("show")
        self.assertEqual(code, 1)
        self.assertIn("is OPEN", out)
        self.verify(PASS)
        code, out, _ = self.run_cli("show")
        self.assertEqual(code, 0)
        self.assertIn("All 1 stage(s) passed", out)
        self.verify(FAIL)
        code, out, _ = self.run_cli("show")
        self.assertEqual(code, 1)
        self.assertIn("FAILING", out)
        self.assertIn("ModuleNotFoundError: imp", out)

    def test_json_output(self):
        self.passing_baseline()
        self.run_cli("open", "python 3.10", "--python", "3.10")
        code, out, _ = self.run_cli("show", "--json")
        view = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual([s["status"] for s in view["stages"]], ["passed", "open"])
        self.assertEqual((view["current_stage"], view["current_status"], view["all_passed"]),
                         (2, "open", False))
        code, out, _ = self.run_cli("verify", "--json", "--", *PASS)
        view = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(view["all_passed"])
        self.assertIn("PASSED", view["message"])

    def test_corrupt_ledgers_are_reported_without_a_traceback(self):
        self.path.parent.mkdir(parents=True)
        for text in ("{not json", "[]", '{"stages": [{"id": 1}]}',
                     '{"stages": [{"id": 1, "name": "baseline", "verifications": [{"passed": true}]}]}'):
            self.path.write_text(text)
            for argv in (("show",), ("open", "next"), ("verify", "--", *PASS)):
                code, _, err = self.run_cli(*argv)
                self.assertEqual(code, 2, (text, argv))
                self.assertIn("cannot read ledger", err)
                self.assertNotIn("Traceback", err)

    def test_no_command_and_help(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            with self.assertRaises(SystemExit) as caught:
                stage_ledger.main([])
            self.assertEqual(caught.exception.code, 2)
            with self.assertRaises(SystemExit) as caught:
                stage_ledger.main(["--help"])
            self.assertEqual(caught.exception.code, 0)
        self.assertIn("Examples:", out.getvalue())
        self.assertIn("Exit codes:", out.getvalue())


class FixtureLedgerTests(LedgerCase):
    FIXTURE = SKILL / "evals" / "files" / "mid-upgrade" / "ledger.json"

    def setUp(self):
        super().setUp()
        self.path = Path(self.tmp.name) / "ledger.json"
        shutil.copy(str(self.FIXTURE), str(self.path))

    def test_fixture_shows_the_failing_3_11_stage(self):
        code, out, _ = self.run_cli("show")
        self.assertEqual(code, 1)
        self.assertIn("Stage 3 'python 3.11' is FAILING", out)
        self.assertIn("has no attribute 'getargspec'", out)
        code, out, _ = self.run_cli("show", "--json")
        view = json.loads(out)
        self.assertEqual([s["status"] for s in view["stages"]], ["passed", "passed", "failing"])

    def test_fixture_refuses_to_open_3_12_and_is_left_unchanged(self):
        before = self.path.read_text()
        code, out, _ = self.run_cli("open", "python 3.12", "--python", "3.12")
        self.assertEqual(code, 1)
        self.assertIn("REFUSED: stage 3 'python 3.11' is failing", out)
        self.assertEqual(self.path.read_text(), before)

    def test_fixture_allows_3_12_once_3_11_passes(self):
        self.assertEqual(self.verify(PASS)[0], 0)
        self.assertEqual(self.run_cli("open", "python 3.12", "--python", "3.12")[0], 0)
        self.assertEqual(len(self.stages()), 4)


if __name__ == "__main__":
    unittest.main()
