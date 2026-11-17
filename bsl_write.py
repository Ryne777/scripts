#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bsl_write.py — заливка прошивки в MSP430 через легаси-BSL (1xx).
Протокол: SLAU319C Table 2-1, SLAA096B. Только стандартная библиотека (Win32, ctypes).

RX Data Block (0x12): AL AH LL LH D1..Dn, n <= 250, адрес и длина чётные -> ACK/NAK.
Каждый записанный блок сразу читается обратно и сверяется; при несовпадении
сегмент стирается (0x16) и пишется заново.

Пароль: сначала векторы из образа (верно для чипа с этой прошивкой, ACK без
стираний), затем FF×32 (верно для чистого флеша; NAK от первого кандидата
сам выполняет mass erase).

Примеры:
  python bsl_write.py COM16 --inv-rst --inv-test firmware.bin
  python bsl_write.py COM16 --inv-rst --inv-test --trace firmware.bin
  python bsl_write.py COM16 --inv-rst --inv-test --write-info firmware.bin
"""
import argparse
import sys
import time

from bsl_core import (open_port, close_port, enter_bsl, probe_version,
                      rx_password, rx_data_block, tx_data_block, erase_segment,
                      load_image, password_candidates, sync,
                      FLASH_START, FLASH_END, INFO_START, INFO_END, BLOCK)


def main():
    p = argparse.ArgumentParser(description="Заливка прошивки через легаси-BSL")
    p.add_argument("port")
    p.add_argument("firmware", help="firmware.bin (бинарный образ) или .hex (Intel HEX)")
    p.add_argument("--inv-rst", action="store_true")
    p.add_argument("--inv-test", action="store_true")
    p.add_argument("--trace", action="store_true")
    p.add_argument("--slow", type=float, default=0.02, metavar="SEC")
    p.add_argument("--gap", type=float, default=0.0,
                   help="базовая пауза между байтами фрейма записи, с (0 = без пауз)")
    p.add_argument("--no-verify", action="store_true", help="не читать блоки обратно после записи")
    p.add_argument("--write-info", action="store_true",
                   help="записать Info-память 0x1000..0x10FF из образа (если там не FF)")
    args = p.parse_args()

    img = load_image(args.firmware)
    print("Образ: %d байт" % len(img))

    h = open_port(args.port)
    try:
        enter_bsl(h, args.inv_rst, args.inv_test, args.trace, args.slow)
        d = probe_version(h, args.gap, args.trace)
        if d is None:
            sys.exit("SYNC/версия не получены — чип не вошёл в BSL.")
        print("BSL version: %x.%02x, семейство: 0x%02X 0x%02X" % (d[10], d[11], d[0], d[1]))

        # Правильный пароль — первым: неудачная попытка вызывает mass erase!
        unlocked = False
        for label, pw in password_candidates(img):
            print("RX Password: пробую %s..." % label)
            if rx_password(h, pw, args.gap, args.trace):
                print("ACK — разблокировано (%s)." % label)
                unlocked = True
                break
            print("NAK: пароль не совпал (mass erase основной флеш).")
        if not unlocked:
            sys.exit("Не разблокировано. Пришлите вывод с --trace.")

        # Опционально: Info-память из образа
        if args.write_info:
            info = img[INFO_START:INFO_END]
            if info == b"\xff" * (INFO_END - INFO_START):
                print("Info-область образа пуста (FF) — писать нечего.")
            else:
                print("Запись Info-памяти 0x%04X..0x%04X из образа..."
                      % (INFO_START, INFO_END - 1))
                for a in range(INFO_START, INFO_END, BLOCK):
                    blk = img[a:a + BLOCK]
                    if blk == b"\xff" * BLOCK:
                        continue
                    if not rx_data_block(h, a, blk, args.gap, args.trace):
                        sys.exit("Запись Info на 0x%04X не удалась." % a)
                print("Info-память записана.")

        blocks_total = (FLASH_END - FLASH_START) // BLOCK
        done = skipped = written = 0
        t0 = time.time()
        for a in range(FLASH_START, FLASH_END, BLOCK):
            blk = img[a:a + BLOCK]
            done += 1
            if blk == b"\xff" * BLOCK:
                skipped += 1
                continue
            ok = False
            for g in (args.gap, max(args.gap, 0.01), 0.05):
                if rx_data_block(h, a, blk, g, args.trace):
                    ok = True
                    break
                sync(h, args.trace)
                print("  Блок 0x%04X: NAK, повтор с паузой %.3f с" % (a, g))
            if not ok:
                sys.exit("Блок 0x%04X не записался после 3 попыток. Пришлите вывод." % a)
            written += 1

            if not args.no_verify:
                back = tx_data_block(h, a, BLOCK, args.gap, args.trace)
                if back is None:
                    sys.exit("Блок 0x%04X: запись принята, но чтение не удалось — пришлите вывод." % a)
                if back != blk:
                    # Могли остаться биты 0 — сегмент не был чистым. Стираем и пишем заново.
                    print("  Блок 0x%04X: не совпал, стираю сегмент и пишу заново..." % a)
                    erase_segment(h, a, 0.02, args.trace)
                    if not rx_data_block(h, a, blk, 0.05, args.trace):
                        sys.exit("Повторная запись 0x%04X не удалась." % a)
                    back = tx_data_block(h, a, BLOCK, args.gap, args.trace)
                    if back != blk:
                        sys.exit("Блок 0x%04X: не совпал даже после стирания. СТОП." % a)
            if done % 16 == 0 or done == blocks_total:
                print("Прогресс: %d/%d блоков (записано %d, пустых пропущено %d), %.1f с"
                      % (done, blocks_total, written, skipped, time.time() - t0))

        vec = tx_data_block(h, 0xFFE0, 32, args.gap, args.trace)
        if vec:
            print("Векторы 0xFFE0..0xFFFF: %s" % vec.hex())
        print("Готово: записано %d блоков за %.1f с. Пустых пропущено %d."
              % (written, time.time() - t0, skipped))
        print("Теперь снимите RST/подайте питание заново — чип загрузит новую прошивку.")
    finally:
        close_port(h, args.inv_rst, args.inv_test)


if __name__ == "__main__":
    main()
