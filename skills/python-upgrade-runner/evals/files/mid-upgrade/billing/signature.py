"""Describe job handlers for the admin page."""
import inspect


def handler_arguments(handler):
    return list(inspect.getargspec(handler).args)


def describe(handler):
    return "%s(%s)" % (handler.__name__, ", ".join(handler_arguments(handler)))
