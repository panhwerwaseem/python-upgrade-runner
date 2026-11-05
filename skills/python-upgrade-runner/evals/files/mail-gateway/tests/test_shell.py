import unittest

from gateway import shell, uploads


class ShellTests(unittest.TestCase):
    def test_paths_with_spaces_are_quoted(self):
        self.assertEqual(
            shell.archive_command("/var/mail/in box", "/backup/mail.tgz"),
            "tar -czf /backup/mail.tgz '/var/mail/in box'")


class UploadTests(unittest.TestCase):
    def test_content_type_and_charset(self):
        self.assertEqual(
            uploads.content_type("text/plain; charset=iso-8859-1"), ("text/plain", "iso-8859-1"))

    def test_charset_defaults_to_utf8(self):
        self.assertEqual(uploads.content_type("image/png"), ("image/png", "utf-8"))


if __name__ == "__main__":
    unittest.main()
