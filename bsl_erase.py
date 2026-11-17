#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bsl_erase.py — стирание памяти MSP430 через легаси-BSL (1xx).
Протокол: SLAU319C Table 2-1, SLAA089C. Только стандартная библиотека (Win32, ctypes).

Команды:
  Mass Erase     0x18: AL=AH=0, слово данных 0xA506 (основной флеш) / 0xA505 (флеш + Info B)
  Erase Segment  0x16: AL AH, слово данных 0xA502 (стирать безусловно)
  Mass Erase разрешён всегда, даже на защищённом BSL. Info A (0x1000..0x107F)
  BSL 1.61 не стирает — сегмент защищён.
  NAK после стирания у BSL 1.60+ может значить и успех (известный глюк erase check),
  поэтому истина проверяется чтением, а не кодом ответа.

Примеры:
  python bsl_erase.py COM16 --inv-rst --inv-test              # стереть основной флеш
  python bsl_erase.py COM16 --inv-rst --inv-test --all        # основной флеш + Info B
  python bsl_erase.py COM16 --inv-rst --inv-test --segment 0x4000  # стереть сегмент 512 байт
  python bsl_erase.py COM16 --inv-rst --inv-test --segment 0x1040  # Info-сегмент B
"""
import argparse
import sys
import time

from bsl_core import (open_port, close_port, enter_bsl, probe_version,
                      rx_password, tx_data_block, erase_segment, mass_erase,
                      BSL_DELAY)


def verify_erased(h, ranges, gap, trace=False, block=128):
    """Читает диапазоны, проверяет, что везде FF. Возвращает список адресов с данными."""
    bad = []
    for (start, end) in ranges:
        a = start
        while a < end:
            n = min(block, end - a)
            data = tx_data_block(h, a, n, gap, trace)
            if data is None:
                return None, "чтение 0x%04X не удалось — верификация невозможна" % a
            if data != b"\xff" * n:
                bad.extend(a + i for i in range(n) if data[i] != 0xFF)
            a += n
            time.sleep(BSL_DELAY)
    return bad, None


def seg_bounds(addr):
    """Границы сегмента: Info — сегменты по 128 байт, основной флеш — по 512."""
    if 0x1000 <= addr < 0x1100:
        return (addr - 0x1000) // 128 * 128 + 0x1000, 128
    return addr // 512 * 512, 512


def main():
    p = argparse.ArgumentParser(description="Стирание памяти MSP430 через легаси-BSL")
    p.add_argument("port")
    p.add_argument("--inv-rst", action="store_true")
    p.add_argument("--inv-test", action="store_true")
    p.add_argument("--trace", action="store_true")
    p.add_argument("--slow", type=float, default=0.02, metavar="SEC")
    p.add_argument("--gap", type=float, default=0.01,
                   help="пауза между байтами фрейма, с")
    p.add_argument("--all", action="store_true",
                   help="Mass Erase 0xA505: основной флеш + Info B (Info A защищён всегда)")
    p.add_argument("--segment", type=lambda x: int(x, 0), action="append", default=[],
                   help="стереть отдельный сегмент (адрес внутри сегмента), можно несколько раз")
    p.add_argument("--no-verify", action="store_true", help="не читать память после стирания")
    p.add_argument("--yes", action="store_true", help="без интерактивного подтверждения")
    args = p.parse_args()

    print("=" * 62)
    print("  ВНИМАНИЕ: стирание удалит прошивку из чипа безвозвратно.")
    print("  Пароль чипа станет FF×32. Info A (калибровки) не трогается")
    print("  командой Mass Erase — он защищён в BSL 1.61.")
    print("=" * 62)
    if not args.yes:
        ans = input("Продолжить? Наберите 'да' или 'yes': ").strip().lower()
        if ans not in ("да", "yes", "y", "д"):
            sys.exit("Отменено.")

    h = open_port(args.port)
    try:
        enter_bsl(h, args.inv_rst, args.inv_test, args.trace, args.slow)
        d = probe_version(h, args.gap, args.trace)
        if d is None:
            sys.exit("SYNC/версия не получены — чип не вошёл в BSL.")
        print("BSL version: %x.%02x, семейство: 0x%02X 0x%02X" % (d[10], d[11], d[0], d[1]))

        if args.segment:
            # Для Erase Segment нужен разблокированный BSL.
            # Пробуем FF×32 (верно после стирания; иначе NAK = mass erase — тоже подготавливает чип).
            print("RX Password FF×32...")
            if not rx_password(h, b"\xff" * 32, args.gap, args.trace):
                print("NAK: флеш был с прошивкой — NAK сам его стёр. Пробую пароль снова.")
                if not rx_password(h, b"\xff" * 32, args.gap, args.trace):
                    sys.exit("Не разблокировано и после стирания — пришлите вывод с --trace.")
            print("Разблокировано.")
            for addr in args.segment:
                seg_start, seg_size = seg_bounds(addr)
                print("Erase Segment 0x%04X (начало сегмента 0x%04X)..." % (addr, seg_start))
                resp = erase_segment(h, seg_start, args.gap, args.trace)
                print("  Ответ: %s (NAK у BSL 1.60+ не всегда значит неудачу — проверим чтением)"
                      % (resp.hex(" ") if resp else "тишина"))
        else:
            print("Mass Erase (0x18) — %s..." % ("флеш + Info B" if args.all else "основной флеш"))
            resp = mass_erase(h, args.all, args.gap, args.trace)
            print("  Ответ: %s (ACK = стёрто; NAK у BSL 1.60+ бывает и после успеха)"
                  % (resp.hex(" ") if resp else "тишина"))

        # После Mass Erase BSL разблокирован сам: память вся FF, пароль FF×32 проходит.
        print("RX Password FF×32 (после стирания должен пройти без стираний)...")
        if not rx_password(h, b"\xff" * 32, args.gap, args.trace):
            sys.exit("Пароль FF не принят — что-то не так, пришлите вывод с --trace.")
        print("Разблокировано.")

        if not args.no_verify:
            ranges = []
            if args.segment:
                for addr in args.segment:
                    seg_start, seg_size = seg_bounds(addr)
                    ranges.append((seg_start, seg_start + seg_size))
            else:
                ranges = [(0x4000, 0x10000)]
                if args.all:
                    ranges.append((0x1080, 0x1100))   # Info B
            print("Верификация (чтение, ожидаем FF)...")
            bad, err = verify_erased(h, ranges, args.gap, args.trace)
            if err:
                sys.exit(err)
            if bad:
                print("НЕ стёрто: %d адресов, первые: %s"
                      % (len(bad), ", ".join("0x%04X" % x for x in bad[:10])))
                sys.exit("Стирание неполное. Пришлите вывод с --trace.")
            for (start, end) in ranges:
                print("  0x%04X..0x%04X: чисто (FF)" % (start, end))
            print("Стирание подтверждено чтением.")

        print("Готово. Пароль чипа теперь FF×32, заливайте прошивку заново: "
              "python bsl_write.py %s --inv-rst --inv-test firmware.bin" % args.port)
    finally:
        close_port(h, args.inv_rst, args.inv_test)


if __name__ == "__main__":
    main()
