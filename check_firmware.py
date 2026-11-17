#!/usr/bin/env python3
# check_firmware.py — проверка firmware.bin перед использованием пароля BSL
import sys

FLASH_LO, FLASH_HI = 0x4000, 0xFFFE

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "firmware.bin"
    data = open(path, "rb").read()
    print("Размер файла: %d байт (0x%X)" % (len(data), len(data)))

    # 1. Не Intel HEX ли это на самом деле
    if data[:1] == b":":
        print("!! Файл начинается с ':' — это похоже на Intel HEX, а не на бинарный образ.")
        print("   Конвертация: objcopy -I ihex -O binary firmware.hex firmware.bin")
        return

    # 2. Хватает ли файла до конца векторов
    if len(data) < 0x10000:
        print("!! Файл короче 0x10000 — векторов прерываний (пароля BSL) в нём нет.")
        print("   Нужен полный образ 64 КБ или пароль из другого источника.")
        return

    # 3. Таблица векторов 0xFFE0-0xFFFF — она же пароль
    vec = data[0xFFE0:0x10000]
    print("\nВекторы прерываний (пароль BSL):")
    bad = 0
    for i in range(0, 32, 2):
        addr = 0xFFE0 + i
        w = vec[i] | (vec[i + 1] << 8)
        ok = FLASH_LO <= w <= FLASH_HI and w % 2 == 0
        mark = "ok" if ok else ("все 0xFF (стёртая память)" if w == 0xFFFF else "??")
        if not ok:
            bad += 1
        print("  0x%04X: %02X %02X -> 0x%04X  %s" % (addr, vec[i], vec[i + 1], w, mark))

    if vec == b"\xFF" * 32:
        print("\nВекторы все 0xFF — это образ стёртой памяти, пароль не годится.")
    elif bad == 0:
        print("\nВсе 16 векторов похожи на адреса кода — файл выглядит цельным образом.")
    else:
        print("\n!! %d векторов не похожи на адреса кода — файл может не совпадать с чипом." % bad)

if __name__ == "__main__":
    main()
