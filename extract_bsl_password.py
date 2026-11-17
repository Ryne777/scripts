#!/usr/bin/env python3
# extract_bsl_password.py
import sys

def main():
    if len(sys.argv) < 2:
        print("Использование: python extract_bsl_password.py firmware.bin")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "rb") as f:
        data = f.read()

    if len(data) < 0x10000:
        # Если файл не на всю флеш (64 КБ), пароль может быть не в конце.
        # Но для F1611 типично, что .bin — полный образ.
        print(f"Файл {path} имеет длину {len(data)} байт — меньше 64 КБ. Пароль может быть не в конце.")
        print("Если это усечённый образ, пароль нужно брать по адресу 0xFFE0 в исходном полном файле.")
        sys.exit(1)

    password = data[0xFFE0:]  # 0xFFE0..0xFFFF = 32 байта
    if len(password) != 32:
        print("Не удалось получить ровно 32 байта для пароля.")
        sys.exit(1)

    print("Пароль (32 байта):")
    print(password.hex())

if __name__ == "__main__":
    main()
