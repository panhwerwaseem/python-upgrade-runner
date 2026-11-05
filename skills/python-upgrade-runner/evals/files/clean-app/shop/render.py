"""Text rendering."""
import warnings

warnings.filterwarnings("error", category=DeprecationWarning)


def table(rows, formatter):
    return "\n".join(formatter.format(name=name, price=price) for name, price in rows)


def summary(rows):
    imp = sum(price for _, price in rows)  # "imp" is a local name here, short for "import total"
    return "total %.2f, see distutils-free build notes in the wiki" % imp
