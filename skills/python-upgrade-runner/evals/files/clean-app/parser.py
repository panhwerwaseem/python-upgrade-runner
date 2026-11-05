"""Command-line parsing for the shop tool. A local module, not the old stdlib parser."""
import argparse


def build():
    cli = argparse.ArgumentParser(prog="shop")
    cli.add_argument("--currency", default="EUR")
    cli.add_argument("items", nargs="*")
    return cli
