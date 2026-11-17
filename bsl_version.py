#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bsl_version.py — проверка входа в BSL и чтение версии загрузчика MSP430.
Самый быстрый тест канала и входной последовательности.

Пример:
  python bsl_version.py COM16 --inv-rst --inv-test
"""
import argparse
import sys

from bsl_core import (open_port, close_port, enter_bsl, probe_version)


def main():
    p = argparse.ArgumentParser(description="Версия легаси-BSL MSP430")
    p.add_argument("port")
    p.add_argument("--inv-rst", action="store_true")
    p.add_argument("--inv-test", action="store_true")
    p.add_argument("--trace", action="store_true")
    p.add_argument("--slow", type=float, default=0.02, metavar="SEC")
    p.add_argument("--gap", type=float, default=0.01, metavar="SEC")
    args = p.parse_args()

    h = open_port(args.port)
    try:
        enter_bsl(h, args.inv_rst, args.inv_test, args.trace, args.slow)
        d = probe_version(h, args.gap, args.trace)
        if d is None:
            sys.exit("SYNC/версия не получены — чип не вошёл в BSL.")
        print("BSL version: %x.%02x, семейство: 0x%02X 0x%02X" % (d[10], d[11], d[0], d[1]))
    finally:
        close_port(h, args.inv_rst, args.inv_test)


if __name__ == "__main__":
    main()
