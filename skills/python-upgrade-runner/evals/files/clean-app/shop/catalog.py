"""Price lookup."""
import importlib
import shlex
from collections.abc import Mapping
from datetime import datetime, timezone

PRICES = {"widget": 2.5, "gadget": 9.9, "gizmo": 12.0}


def price_of(name, prices=PRICES):
    if not isinstance(prices, Mapping):
        raise TypeError("prices must be a mapping")
    return prices[name]


def stamp(clock=None):
    """Timestamp for an export. A clock object with utcnow() can be injected in tests."""
    if clock is not None:
        return clock.utcnow().isoformat()
    return datetime.now(timezone.utc).isoformat()


def export_command(path):
    return "shop-export --out %s" % shlex.quote(path)


def reload_prices(module):
    # The old code called imp.reload(); it now uses importlib.
    return importlib.reload(module)
