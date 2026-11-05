import os
import tempfile
import unittest

from inventory import config


class ConfigTests(unittest.TestCase):
    def write_ini(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".ini", delete=False)
        self.addCleanup(os.remove, handle.name)
        handle.write(text)
        handle.close()
        return handle.name

    def test_defaults_apply_when_file_is_empty(self):
        settings = config.load(self.write_ini(""))
        self.assertEquals(settings["warehouse"], "main")

    def test_file_overrides_defaults(self):
        settings = config.load(self.write_ini("[DEFAULT]\nlow_stock = 9\n"))
        self.assertEquals(settings["low_stock"], "9")

    def test_overrides_must_be_a_mapping(self):
        with self.assertRaises(TypeError):
            config.load(self.write_ini(""), overrides=[("warehouse", "north")])


if __name__ == "__main__":
    unittest.main()
