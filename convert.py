import binascii

BIN_FILE = 'firmware.bin'
START_ADDR = 0x4000   # стартовый адрес во flash (для MSP430F1611 — 0x4000)


def intel_hex_record(addr, rectype, data=b''):
    """Формирует одну строку Intel HEX с контрольной суммой."""
    length = len(data)
    # Сумма полей: count + addr_hi + addr_lo + type + данные
    s = length + (addr >> 8 & 0xFF) + (addr & 0xFF) + rectype + sum(data)
    checksum = (-s) & 0xFF  # дополнение до нуля
    return f':{length:02X}{addr:04X}{rectype:02X}{data.hex().upper()}{checksum:02X}'


def bin_to_ihex(data, start_addr, out_path):
    lines = []
    pos = 0
    while pos < len(data):
        chunk = data[pos:pos + 16]          # до 16 байт в записи — стандарт
        lines.append(intel_hex_record(start_addr + pos, 0x00, chunk))
        pos += len(chunk)
    lines.append(intel_hex_record(0, 0x01))  # обязательный EOF-рекорд
    with open(out_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def bin_to_ti_txt(data, start_addr, out_path):
    lines = [f'@{start_addr:04X}']
    pos = 0
    while pos < len(data):
        chunk = data[pos:pos + 16]
        lines.append(' '.join(f'{b:02X}' for b in chunk))
        pos += len(chunk)
    lines.append('q')                        # завершающий символ формата
    with open(out_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


with open(BIN_FILE, 'rb') as f:
    data = f.read()

print(f'Адреса прошивки: 0x{START_ADDR:04X} - 0x{START_ADDR + len(data) - 1:04X}')

bin_to_ihex(data, START_ADDR, 'firmware.hex')
bin_to_ti_txt(data, START_ADDR, 'firmware.txt')
print('Готово: firmware.hex и firmware.txt')
