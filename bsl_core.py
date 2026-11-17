#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bsl_core.py — общий код для работы с легаси-BSL MSP430 (семейства 1xx/2xx/4xx).
Протокол: SLAU319C Table 2-1, SLAA096B. Только стандартная библиотека (Win32, ctypes).

Используется скриптами bsl_version.py, bsl_read.py, bsl_write.py, bsl_erase.py.
Положите его в ту же папку, что и сами скрипты.
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

# --- Win32 ---
GENERIC_READWRITE = 0xC0000000
OPEN_EXISTING     = 3
SETDTR, CLRDTR    = 5, 6
SETRTS, CLRRTS    = 3, 4
PURGE_ALL         = 0x000F

# --- Протокол (легаси-BSL) ---
BSL_SYNC  = 0x80
BSL_ACK   = 0x90
BSL_NAK   = 0xA0
BSL_DELAY = 0.005

CMD_RXPW      = 0x10   # RX Password
CMD_RXBLK     = 0x12   # RX Data Block (запись)
CMD_TXDATA    = 0x14   # TX Data Block (чтение)
CMD_ERASE_SEG = 0x16   # Erase Segment
CMD_MASSERASE = 0x18   # Mass Erase
CMD_VERSION   = 0x1E   # BSL version

# --- Карта памяти MSP430F1611 ---
FLASH_START = 0x4000
FLASH_END   = 0x10000   # 48 КБ основного флеша
INFO_START  = 0x1000
INFO_END    = 0x1100    # 256 байт Info (Info A + Info B)
BLOCK       = 128       # чётный блок, <= 250 (лимит данных фрейма RX Data Block)

kernel32 = ctypes.windll.kernel32


class DCB(ctypes.Structure):
    _fields_ = [
        ("DCBlength", wt.DWORD), ("BaudRate", wt.DWORD), ("flags", wt.DWORD),
        ("wReserved", wt.WORD), ("XonLim", wt.WORD), ("XoffLim", wt.WORD),
        ("ByteSize", wt.BYTE), ("Parity", wt.BYTE), ("StopBits", wt.BYTE),
        ("XonChar", ctypes.c_char), ("XoffChar", ctypes.c_char),
        ("ErrorChar", ctypes.c_char), ("EofChar", ctypes.c_char),
        ("EvtChar", ctypes.c_char), ("wReserved1", wt.WORD),
    ]


class COMMTIMEOUTS(ctypes.Structure):
    _fields_ = [
        ("ReadIntervalTimeout",         wt.DWORD),
        ("ReadTotalTimeoutMultiplier",  wt.DWORD),
        ("ReadTotalTimeoutConstant",    wt.DWORD),
        ("WriteTotalTimeoutMultiplier", wt.DWORD),
        ("WriteTotalTimeoutConstant",   wt.DWORD),
    ]


# --- Последовательный порт (Win32) ---

def open_port(name, baud=9600):
    h = kernel32.CreateFileW("\\\\.\\%s" % name, GENERIC_READWRITE, 0, None,
                             OPEN_EXISTING, 0, None)
    if h in (-1, 0xFFFFFFFF):
        sys.exit("Не удалось открыть %s (WinError %s). Порт занят?" % (name, kernel32.GetLastError()))
    dcb = DCB(); dcb.DCBlength = ctypes.sizeof(DCB)
    if not kernel32.GetCommState(h, ctypes.byref(dcb)): sys.exit("GetCommState failed")
    dcb.BaudRate = baud; dcb.ByteSize = 8
    dcb.Parity = 2          # EVENPARITY
    dcb.StopBits = 0
    dcb.flags = 0x0001 | 0x0002
    if not kernel32.SetCommState(h, ctypes.byref(dcb)): sys.exit("SetCommState failed")
    to = COMMTIMEOUTS()
    to.ReadIntervalTimeout = 0xFFFFFFFF
    to.ReadTotalTimeoutMultiplier = 0
    to.ReadTotalTimeoutConstant = 0
    to.WriteTotalTimeoutMultiplier = 0
    to.WriteTotalTimeoutConstant = 500
    kernel32.SetCommTimeouts(h, ctypes.byref(to))
    return h


def set_lines(h, dtr, rts, inv_rst=False, inv_test=False):
    kernel32.EscapeCommFunction(h, SETDTR if dtr ^ inv_rst else CLRDTR)
    kernel32.EscapeCommFunction(h, SETRTS if rts ^ inv_test else CLRRTS)


def flush_in(h):
    kernel32.PurgeComm(h, PURGE_ALL)


def write(h, data):
    n = wt.DWORD()
    kernel32.WriteFile(h, data, len(data), ctypes.byref(n), None)
    return n.value


def write_slow(h, data, gap=0.01):
    for b in data:
        write(h, bytes([b]))
        time.sleep(gap)


def read(h, count, timeout=0.5):
    buf = ctypes.create_string_buffer(count)
    got = wt.DWORD()
    out = b""
    deadline = time.time() + timeout
    while len(out) < count and time.time() < deadline:
        if kernel32.ReadFile(h, buf, count - len(out), ctypes.byref(got), None) and got.value:
            out += buf.raw[:got.value]
        else:
            time.sleep(0.01)
    return out


def close_port(h, inv_rst=False, inv_test=False):
    set_lines(h, False, False, inv_rst, inv_test)
    kernel32.CloseHandle(h)


# --- Протокол BSL ---

def xorchk(data):
    even = odd = 0
    for i, b in enumerate(data):
        if i & 1: odd ^= b
        else:     even ^= b
    return (~even) & 0xFF, (~odd) & 0xFF


def frame(cmd, payload):
    body = bytes([0x80, cmd, len(payload), len(payload)]) + payload
    return body + bytes(xorchk(body))


def sync(h, trace=False):
    flush_in(h)
    for _ in range(5):
        write(h, bytes([BSL_SYNC]))
        if read(h, 1, timeout=0.3) == bytes([BSL_ACK]):
            time.sleep(BSL_DELAY)
            return True
        time.sleep(0.05)
    return False


def enter_bsl(h, inv_rst, inv_test, trace=False, slow=0.02):
    def tick(): time.sleep(slow)
    def st(dtr, rts):
        set_lines(h, dtr, rts, inv_rst, inv_test)
        if trace:
            print("  DTR(RST)=%-2d RTS(TEST)=%-2d" % (dtr, rts))
    st(0, 0); tick()
    st(0, 1); tick(); st(0, 0); tick()
    st(0, 1); tick(); st(0, 0); tick()
    st(1, 0); tick()
    return True


def send_cmd(h, cmd, payload, gap=0.0, timeout=2.0, trace=False):
    """SYNC перед каждой командой (bslTxRx, SLAA096B) -> фрейм -> ответ."""
    if not sync(h, trace):
        if trace:
            print("  SYNC не прошёл")
        return b""
    fr = frame(cmd, payload)
    if gap > 0:
        write_slow(h, fr, gap)
    else:
        write(h, fr)
    first = read(h, 1, timeout)
    if trace:
        print("  Ответ: %s" % (first.hex(" ") if first else "тишина"))
    if not first:
        return b""
    if first[0] in (BSL_ACK, BSL_NAK):
        return first
    return first + read(h, 3, timeout)


def probe_version(h, gap, trace=False):
    """CMD 0x1E. Ответ: ACK + фрейм 80 1E 04 04 d1..d4 chk chk
    ИЛИ сразу фрейм 80 1E 04 04 ... (без ACK) — обрабатываются оба варианта.
    Заголовок дочитывается строго до 4 байт, данные + контрольная сумма —
    ровно одним куском n+2 (лишний байт ломает разбор)."""
    resp = send_cmd(h, CMD_VERSION, bytes(4), gap, trace=trace)
    if not resp or resp[0] == BSL_NAK:
        return None
    if resp[0] == BSL_ACK:
        hdr = read(h, 4, 2.0)
    else:
        hdr = bytes(resp)
        if len(hdr) < 4:
            hdr += read(h, 4 - len(hdr), 1.0)
    if len(hdr) < 4 or hdr[0] != BSL_SYNC or hdr[2] != hdr[3]:
        return None
    n = hdr[2]
    rest = read(h, n + 2, 2.0)
    if len(rest) < n + 2 or xorchk(hdr + rest[:n]) != (rest[n], rest[n + 1]):
        return None
    return rest[:n]


def rx_password(h, pw, gap=0.05, trace=False):
    """RX Password (0x10): 4 байта-заглушки + 32 байта пароля. ACK = разблокировано.
    ВНИМАНИЕ: NAK = mass erase основного флеша!"""
    resp = send_cmd(h, CMD_RXPW, b"\x00\x00\x00\x00" + pw, gap, timeout=15.0, trace=trace)
    return resp == bytes([BSL_ACK])


def tx_data_block(h, addr, n, gap, trace=False):
    """Чтение n байт (0x14). Ответ: ACK + фрейм или сразу фрейм. Оба варианта."""
    payload = bytes([addr & 0xFF, (addr >> 8) & 0xFF, n, 0])
    resp = send_cmd(h, CMD_TXDATA, payload, gap, trace=trace)
    if not resp:
        return None
    buf = bytearray(resp)
    deadline = time.time() + 4.0
    while len(buf) < 5 and time.time() < deadline:
        chunk = read(h, 5 - len(buf), 0.5)
        if chunk:
            buf += chunk
    if buf[0] == BSL_ACK:
        buf = buf[1:]
    if len(buf) < 4 or buf[0] != BSL_SYNC:
        return None
    hdr = bytes(buf[:4])
    if hdr[2] != hdr[3]:
        return None
    n2 = hdr[2]
    already = len(buf) - 4
    rest = bytes(buf[4:]) + read(h, n2 + 2 - already, 3.0)
    if len(rest) < n2 + 2 or xorchk(hdr + rest[:n2]) != (rest[n2], rest[n2 + 1]):
        return None
    return rest[:n2]


def rx_data_block(h, addr, data, gap, trace=False):
    """Запись блока (0x12): AL AH LL LH D1..Dn. ACK = записано."""
    payload = bytes([addr & 0xFF, (addr >> 8) & 0xFF, len(data) & 0xFF, 0]) + data
    resp = send_cmd(h, CMD_RXBLK, payload, gap, timeout=5.0, trace=trace)
    return resp == bytes([BSL_ACK])


def erase_segment(h, addr, gap=0.02, trace=False):
    """Erase Segment (0x16): AL AH 02 A5 (стирание безусловно).
    У BSL 1.60+ после стирания идёт erase check; NAK может значить и успех —
    истинный результат проверяйте чтением."""
    payload = bytes([addr & 0xFF, (addr >> 8) & 0xFF, 0x02, 0xA5])
    resp = send_cmd(h, CMD_ERASE_SEG, payload, gap, timeout=15.0, trace=trace)
    return resp


def mass_erase(h, info_too, gap, trace=False):
    """Mass Erase (0x18): AL=AH=0. Слово данных: 0xA506 — основной флеш,
    0xA505 — основной флеш + Info B. Info A не стирается (защищён в BSL)."""
    d2 = 0x05 if info_too else 0x06
    resp = send_cmd(h, CMD_MASSERASE, bytes([0x00, 0x00, d2, 0xA5]),
                    gap, timeout=15.0, trace=trace)
    return resp


def read_range(h, addr, length, gap, trace=False, block=BLOCK, label=""):
    """Читает диапазон блоками и печатает прогресс каждые 16 блоков.
    Возвращает (bytes, None) или (None, строка_ошибки)."""
    out = bytearray()
    a = addr
    total = (length + block - 1) // block
    idx = 0
    while a < addr + length:
        n = min(block, addr + length - a)
        data = tx_data_block(h, a, n, gap, trace)
        if data is None:
            return None, "чтение на 0x%04X не удалось" % a
        out += data
        idx += 1
        if idx % 16 == 0 or idx == total:
            print("  Чтение %s: %d/%d блоков (адрес 0x%04X)" % (label or "память", idx, total, a))
        a += n
        time.sleep(BSL_DELAY)
    return bytes(out), None


# --- Файлы образов ---

def load_image(path):
    """Бинарный образ или Intel HEX -> bytes длиной 0x10000 (незаполненное = FF)."""
    data = open(path, "rb").read()
    if data[:1] != b":":
        if len(data) > 0x10000:
            sys.exit("Файл больше 64 КБ (%d байт) — что-то не так." % len(data))
        if len(data) < 0x10000:
            print("Файл короче 64 КБ (%d байт): дополняю до 0x10000 байтами FF." % len(data))
        return data.ljust(0x10000, b"\xff")
    img = bytearray(b"\xff" * 0x10000)
    upper = 0
    for line in data.decode("ascii", "replace").splitlines():
        line = line.strip()
        if not line.startswith(":"):
            continue
        n = int(line[1:3], 16)
        addr = int(line[3:7], 16)
        typ = int(line[7:9], 16)
        payload = bytes.fromhex(line[9:9 + 2 * n])
        if typ == 0x00:
            a = upper + addr
            img[a:a + n] = payload
        elif typ == 0x01:
            break
        elif typ == 0x02:
            upper = int(line[9:13], 16) << 4
        elif typ == 0x04:
            upper = int(line[9:13], 16) << 16
    return bytes(img)


def password_candidates(img=None):
    """Кандидаты пароля в безопасном порядке.
    Правильный (векторы 0xFFE0..0xFFFF из образа) — первым: неверный пароль
    вызывает mass erase! FF×32 верен только для чистого (стёртого) флеша."""
    cands = []
    if img is not None and img[0xFFE0:0x10000] != b"\xff" * 32:
        cands.append(("из образа (векторы)", img[0xFFE0:0x10000]))
    cands.append(("FF×32", b"\xff" * 32))
    return cands
