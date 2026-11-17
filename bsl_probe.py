#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bsl_probe.py — многократные попытки входа в BSL и SYNC. Диагностика."""

import sys
import time
from bsl_core import (
    open_port,
    close_port,
    enter_bsl,
    set_lines,
    flush_in,
    write,
    read,
    BSL_SYNC,
    BSL_ACK,
)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM16"
    inv_rst = "--inv-rst" in sys.argv
    inv_test = "--inv-test" in sys.argv
    h = open_port(port)
    try:
        for attempt in range(1, 11):
            print("Попытка %d: вход..." % attempt)
            enter_bsl(h, inv_rst, inv_test, trace=False, slow=0.03)
            got_any = b""
            for _ in range(15):
                flush_in(h)
                write(h, bytes([BSL_SYNC]))
                r = read(h, 1, timeout=0.15)
                if r:
                    got_any += r
                    if r == bytes([BSL_ACK]):
                        break
                time.sleep(0.05)
            if got_any:
                print("  Ответ чипа: %s" % got_any.hex(" "))
                if bytes([BSL_ACK]) in got_any:
                    print("  SYNC ПОЛУЧЕН — чип в BSL.")
                    return
            else:
                print("  Тишина (15 SYNC-байтов без ответа)")
        print("Итог: за 10 попыток ни одного байта от чипа.")
        print(
            "Дальше искать в железе: кварц 32768 Гц, питание, пайка, маркировка чипа."
        )
    finally:
        set_lines(h, False, False, inv_rst, inv_test)
        close_port(h)


if __name__ == "__main__":
    main()
