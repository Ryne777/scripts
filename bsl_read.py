#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bsl_read.py — чтение памяти MSP430 через легаси-BSL (1xx).
Протокол: SLAU319C Table 2-1, SLAA096B. Только стандартная библиотека (Win32, ctypes).

Читает Info-память (0x1000..0x10FF) и векторы (0xFFE0..0xFFFF);
с --dump — весь основной флеш 0x4000..0xFFFF в файл flash_dump.bin.

ВНИМАНИЕ про пароль: неверный пароль вызывает mass erase основного флеша.
Если в чипе уже есть прошивка — указывайте --pwfile firmware.bin: пароль
возьмётся из векторов образа и пройдёт с первого раза, без стираний.
Без --pwfile скрипт шлёт FF×32 — это безопасно только для чистого флеша.

Примеры:
  python bsl_read.py COM16 --inv-rst --inv-test --pwfile firmware.bin
  python bsl_read.py COM16 --inv-rst --inv-test --pwfile firmware.bin --dump
"""
import argparse
import sys
import time

from bsl_core import (open_port, close_port, enter_bsl, probe_version,
                      rx_password, tx_data_block, read_range, load_image,
                      password_candidates,
                      FLASH_START, FLASH_END, INFO_START, INFO_END,
                      BSL_DELAY)


def hexdump(data, base):
    for i in range(0, len(data), 16):
        print("  0x%04X: %s" % (base + i, data[i:i + 16].hex(" ")))


def main():
    p = argparse.ArgumentParser(description="Чтение памяти MSP430 через легаси-BSL")
    p.add_argument("port")
    p.add_argument("--inv-rst", action="store_true")
    p.add_argument("--inv-test", action="store_true")
    p.add_argument("--trace", action="store_true")
    p.add_argument("--slow", type=float, default=0.02, metavar="SEC")
    p.add_argument("--gap", type=float, default=0.01,
                   help="пауза между байтами фрейма, с (0 = без пауз)")
    p.add_argument("--pwfile", metavar="FILE",
                   help="образ прошивки (.bin/.hex) — пароль берётся из его векторов")
    p.add_argument("--dump", action="store_true",
                   help="прочитать весь основной флеш 0x4000..0xFFFF и сохранить в flash_dump.bin")
    args = p.parse_args()

    h = open_port(args.port)
    try:
        enter_bsl(h, args.inv_rst, args.inv_test, args.trace, args.slow)
        d = probe_version(h, args.gap, args.trace)
        if d is None:
            sys.exit("SYNC/версия не получены — чип не вошёл в BSL.")
        print("BSL version: %x.%02x, семейство: 0x%02X 0x%02X" % (d[10], d[11], d[0], d[1]))

        # Кандидаты пароля: из образа (если задан) — первым, FF×32 — последним.
        # Неверный пароль = mass erase, поэтому правильный пробуем раньше.
        img = load_image(args.pwfile) if args.pwfile else None
        cands = password_candidates(img)
        if img is None:
            print("ВНИМАНИЕ: --pwfile не задан. Если в чипе уже есть прошивка, "
                  "неверный пароль (FF×32) её сотрёт!")
        unlocked = False
        for label, pw in cands:
            print("RX Password: пробую %s..." % label)
            if rx_password(h, pw, args.gap, args.trace):
                print("ACK — разблокировано (%s)." % label)
                unlocked = True
                break
            print("NAK: пароль не совпал (mass erase основной флеш).")
        if not unlocked:
            sys.exit("Не разблокировано. Пришлите вывод с --trace.")

        print("Info-память 0x%04X..0x%04X:" % (INFO_START, INFO_END - 1))
        info, err = read_range(h, INFO_START, INFO_END - INFO_START, args.gap,
                               args.trace, label="Info")
        if err:
            sys.exit("Info: %s" % err)
        hexdump(info, INFO_START)
        if info == b"\xff" * (INFO_END - INFO_START):
            print("Info-память пуста (все FF) — калибровки стёрты.")
        with open("info_a.bin", "wb") as f:
            f.write(info)

        print("Векторы 0xFFE0..0xFFFF:")
        vec, err = read_range(h, 0xFFE0, 32, args.gap, args.trace, label="Векторы")
        if err:
            sys.exit("Векторы: %s" % err)
        hexdump(vec, 0xFFE0)

        if args.dump:
            print("Основной флеш 0x%04X..0x%04X (--dump)..." % (FLASH_START, FLASH_END - 1))
            flash, err = read_range(h, FLASH_START, FLASH_END - FLASH_START,
                                    args.gap, args.trace, label="Флеш")
            if err:
                sys.exit("Флеш: %s" % err)
            with open("flash_dump.bin", "wb") as f:
                f.write(flash)
            print("Сохранено: flash_dump.bin (%d байт)" % len(flash))

        print("Чтение завершено.")
    finally:
        close_port(h, args.inv_rst, args.inv_test)


if __name__ == "__main__":
    main()
