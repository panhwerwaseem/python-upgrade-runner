import os
import tempfile
import unittest

from inventory import compat, plugins, report


def reorder(item, quantity):
    return item, quantity


class ReportTests(unittest.TestCase):
    def test_generated_at_is_a_utc_timestamp(self):
        self.assertRegex(report.generated_at(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_describe_lists_arguments(self):
        self.assertEqual(report.describe(reorder), "reorder(item, quantity)")

    def test_low_stock_is_sorted(self):
        self.assertEqual(report.low_stock({"nut": 2, "bolt": 1, "gear": 40}, 5), ["bolt", "nut"])

    def test_functions_are_callable(self):
        self.assertTrue(compat.is_callable(reorder))


class PluginTests(unittest.TestCase):
    def test_plugin_file_is_loaded(self):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "bulk_discount.py")
        with open(path, "w") as handle:
            handle.write("RATE = 0.1\n")
        self.addCleanup(os.rmdir, folder)
        self.addCleanup(os.remove, path)
        self.assertEqual(plugins.load_plugin(path).RATE, 0.1)


if __name__ == "__main__":
    unittest.main()
