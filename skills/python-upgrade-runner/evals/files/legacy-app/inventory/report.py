"""Stock reports."""
import datetime
import inspect


def generated_at():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def describe(func):
    spec = inspect.getargspec(func)
    return "%s(%s)" % (func.__name__, ", ".join(spec.args))


def low_stock(levels, threshold):
    return sorted(name for name, count in levels.items() if count < threshold)
