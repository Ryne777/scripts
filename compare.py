# compare.py
fw = open("firmware.bin", "rb").read()
dmp = open("flash_dump.bin", "rb").read()   # основной флеш: 0x4000..0xFFFF
info = open("info_a.bin", "rb").read()      # Info: 0x1000..0x10FF

def diff(name, a, b):
    if a == b:
        print("%s: OK — побайтово совпадает (%d байт)" % (name, len(a)))
        return
    bad = [i for i in range(len(a)) if a[i] != b[i]]
    print("%s: РАЗЛИЧИЯ в %d байтах, первые: %s"
          % (name, len(bad), ", ".join("0x%04X" % x for x in bad[:10])))

diff("Основной флеш 0x4000..0xFFFF", fw[0x4000:0x10000], dmp)
diff("Info-память 0x1000..0x10FF", fw[0x1000:0x1100], info)
