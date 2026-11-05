"""Entry point: python3 cli.py --currency USD widget gadget"""
import sys

import parser
from shop import catalog, render


def main(argv=None):
    args = parser.build().parse_args(argv)
    rows = [(name, catalog.price_of(name)) for name in args.items]
    print(render.table(rows, "{name:<10} {price:>8.2f} " + args.currency))
    return 0


if __name__ == "__main__":
    sys.exit(main())
