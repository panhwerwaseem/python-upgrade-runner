import unittest

from shop import catalog, render


class FixedClock:
    def utcnow(self):
        from datetime import datetime
        return datetime(2026, 1, 2, 3, 4, 5)


class CatalogTests(unittest.TestCase):
    def test_price_of_known_item(self):
        self.assertEqual(catalog.price_of("widget"), 2.5)

    def test_stamp_uses_injected_clock(self):
        self.assertEqual(catalog.stamp(FixedClock()), "2026-01-02T03:04:05")

    def test_export_command_quotes_path(self):
        self.assertEqual(catalog.export_command("my file.csv"), "shop-export --out 'my file.csv'")

    def test_table_renders_rows(self):
        self.assertEqual(render.table([("widget", 2.5)], "{name}={price:.1f}"), "widget=2.5")

    def test_summary_totals_rows(self):
        self.assertTrue(render.summary([("a", 1.0), ("b", 2.0)]).startswith("total 3.00"))


if __name__ == "__main__":
    unittest.main()
