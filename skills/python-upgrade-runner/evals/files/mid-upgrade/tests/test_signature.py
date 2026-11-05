import unittest

from billing import signature


def charge(account, amount):
    return account, amount


def refund(account, amount, reason):
    return account, amount, reason


class SignatureTests(unittest.TestCase):
    def test_arguments_are_listed_in_order(self):
        self.assertEqual(signature.handler_arguments(refund), ["account", "amount", "reason"])

    def test_describe_formats_name_and_arguments(self):
        self.assertEqual(signature.describe(charge), "charge(account, amount)")


if __name__ == "__main__":
    unittest.main()
