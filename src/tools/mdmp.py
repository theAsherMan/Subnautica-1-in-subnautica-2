import struct, sys, ntpath
p = sys.argv[1]
d = open(p, 'rb').read()
sig, ver, nstreams, dirrva = struct.unpack_from('<4sIII', d, 0)
print("signature", sig, "streams", nstreams)
streams = {}
for i in range(nstreams):
    st, size, rva = struct.unpack_from('<III', d, dirrva + 12*i)
    streams.setdefault(st, []).append((size, rva))
def mstring(rva):
    n = struct.unpack_from('<I', d, rva)[0]
    return d[rva+4:rva+4+n].decode('utf-16le', 'replace')
mods = []
if 4 in streams:
    size, rva = streams[4][0]
    n = struct.unpack_from('<I', d, rva)[0]
    for i in range(n):
        off = rva + 4 + 108*i
        base, simg, cks, ts, namerva = struct.unpack_from('<QIIII', d, off)
        mods.append((base, simg, mstring(namerva)))
print("modules:", len(mods))
def modfor(addr):
    for base, size, name in mods:
        if base <= addr < base + size:
            return name, addr - base
    return None, None
if 6 in streams:
    size, rva = streams[6][0]
    tid, _al, code, flags, rec, addr, nparams, _u = struct.unpack_from('<IIIIQQII', d, rva)
    info = struct.unpack_from('<15Q', d, rva + 8 + 32)
    print("exception thread %d code 0x%08X at 0x%X" % (tid, code, addr))
    name, off = modfor(addr)
    print("  in module:", name, "offset 0x%X" % off if off is not None else "")
    if code == 0xC0000005:
        print("  access violation: %s address 0x%X" % ({0:"READ",1:"WRITE",8:"EXEC"}.get(info[0], info[0]), info[1]))
    # thread context -> RSP, then scan stack for return addresses into known modules
    ctx_size, ctx_rva = struct.unpack_from('<II', d, rva + 8 + 152)
    # CONTEXT (AMD64): Rsp at offset 0x98, Rip at 0xF8
    rsp = struct.unpack_from('<Q', d, ctx_rva + 0x98)[0]
    rip = struct.unpack_from('<Q', d, ctx_rva + 0xF8)[0]
    print("  rip 0x%X rsp 0x%X" % (rip, rsp))
    # memory list stream (5) or Memory64 (9) to read stack
    mem = []
    if 9 in streams:
        size, mrva = streams[9][0]
        n, baserva = struct.unpack_from('<QQ', d, mrva)
        cur = baserva
        for i in range(n):
            start, msz = struct.unpack_from('<QQ', d, mrva + 16 + 16*i)
            mem.append((start, msz, cur)); cur += msz
    if 5 in streams:
        size, mrva = streams[5][0]
        n = struct.unpack_from('<I', d, mrva)[0]
        for i in range(n):
            start, msz, drva = struct.unpack_from('<QII', d, mrva + 4 + 16*i)
            mem.append((start, msz, drva))
    def read(addr, n):
        for start, msz, frva in mem:
            if start <= addr and addr + n <= start + msz:
                o = frva + (addr - start)
                return d[o:o+n]
        return None
    print("  stack scan (return addresses into modules):")
    shown = 0
    for i in range(0, 4096, 8):
        b = read(rsp + i, 8)
        if not b: break
        v = struct.unpack('<Q', b)[0]
        name, off = modfor(v)
        if name and ('UE4SS' in name or 'Subnautica' in name or 'lua' in name.lower()):
            print("    rsp+0x%04X  %s+0x%X" % (i, name.split(chr(92))[-1], off))
            shown += 1
            if shown >= 30: break
