"""Names that moved between Python versions."""
try:
    from collections.abc import Callable
except ImportError:  # very old interpreters
    from collections import Callable


def is_callable(value):
    return isinstance(value, Callable)
