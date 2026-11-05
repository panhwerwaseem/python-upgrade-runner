"""Load settings from an INI file."""
from collections import Mapping
from configparser import SafeConfigParser

DEFAULTS = {"warehouse": "main", "low_stock": "5"}


def load(path, overrides=None):
    parser = SafeConfigParser(DEFAULTS)
    parser.read(path)
    settings = dict(parser.items("DEFAULT"))
    if overrides is not None:
        if not isinstance(overrides, Mapping):
            raise TypeError("overrides must be a mapping")
        settings.update(overrides)
    return settings
