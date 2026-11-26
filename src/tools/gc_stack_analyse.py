#!/usr/bin/env python3
"""Offline analysis of gc_stack_sampler.py output (2026-11-24). Stdlib only (python -I is fine).
Usage: python gc_stack_analyse.py <run dir> [--exe <path to exe>] [--top 15] [--classmap <classmap.tsv>]
Reads <run>/stack_samples.jsonl, stack_samples.bin, stack_modules.json. Parses the exe PE on disk (sections, .pdata
RUNTIME_FUNCTION table with chained unwind entries folded into the parent, no PDB). Reports:
  - RIP-in-function histogram, and 'appears as a call-preceded return address on the stack' histogram (% of samples);
  - for the top functions, the string literals referenced via RIP-relative LEA/MOV disp32 (ASCII and UTF-16LE);
  - tier 2: for pointer-like register / stack values whose first qword is an exe .rdata address (vtable), the qword at +0x10
    (ClassPrivate) histogram, resolved through classmap.tsv (columns: address hex, class full name) if present."""
import argparse, collections, json, os, struct, sys, bisect


class PE:
    def __init__(s, path):
        s.d = open(path, "rb").read()
        d = s.d
        e = struct.unpack_from("<I", d, 0x3C)[0]
        assert d[e:e + 4] == b"PE\0\0"
        nsec, = struct.unpack_from("<H", d, e + 6)
        optsz, = struct.unpack_from("<H", d, e + 20)
        o = e + 24
        assert struct.unpack_from("<H", d, o)[0] == 0x20B
        s.image_base = struct.unpack_from("<Q", d, o + 24)[0]
        s.size_of_image = struct.unpack_from("<I", d, o + 56)[0]
        dd = o + 112
        s.exc = struct.unpack_from("<II", d, dd + 3 * 8)
        s.exp = struct.unpack_from("<II", d, dd + 0)
        s.secs = []
        so = o + optsz
        for i in range(nsec):
            nm, vs, va, rs, ro = struct.unpack_from("<8sIIII", d, so + i * 40)
            ch = struct.unpack_from("<I", d, so + i * 40 + 36)[0]
            s.secs.append((nm.rstrip(b"\0").decode(), va, vs, ro, rs, ch))
        s.funcs = []
        s._load_pdata()

    def off(s, rva):
        for nm, va, vs, ro, rs, ch in s.secs:
            if va <= rva < va + max(vs, rs):
                o = ro + rva - va
                return o if rva - va < rs else None
        return None

    def sec(s, rva):
        for x in s.secs:
            if x[1] <= rva < x[1] + max(x[2], x[4]):
                return x[0]
        return None

    def bytes_at(s, rva, n):
        o = s.off(rva)
        return s.d[o:o + n] if o is not None else b""

    def _load_pdata(s):
        rva, size = s.exc
        raw = s.bytes_at(rva, size)
        n = len(raw) // 12
        ents = [struct.unpack_from("<III", raw, i * 12) for i in range(n)]
        begins = {b: (b, e, u) for b, e, u in ents}
        out = []
        for b, e, u in ents:
            root = b
            for _ in range(8):
                ui = u & ~1
                hdr = s.bytes_at(ui, 4)
                if len(hdr) < 4:
                    break
                flags = hdr[0] >> 3
                if not flags & 4:
                    break
                cnt = hdr[2]
                p = ui + 4 + ((cnt + 1) & ~1) * 2
                pb = s.bytes_at(p, 12)
                if len(pb) < 12:
                    break
                b2, e2, u2 = struct.unpack("<III", pb)
                root = b2; u = u2
            out.append((b, e, root))
        out.sort()
        s.funcs = out
        s.fb = [f[0] for f in out]

    def func_of(s, rva):
        i = bisect.bisect_right(s.fb, rva) - 1
        if i >= 0 and s.funcs[i][0] <= rva < s.funcs[i][1]:
            return s.funcs[i][2]
        return None

    def strings_of(s, fbegin):
        """Strings referenced by RIP-relative LEA/MOV within all pdata ranges whose root is fbegin."""
        res = []
        for b, e, root in s.funcs:
            if root != fbegin:
                continue
            code = s.bytes_at(b, e - b)
            for i in range(len(code) - 6):
                op = code[i]
                if op in (0x8D, 0x8B) and (code[i + 1] & 0xC7) == 0x05 and i >= 1 and (code[i - 1] & 0xF0) == 0x40:
                    disp = struct.unpack_from("<i", code, i + 2)[0]
                    tgt = b + i + 6 + disp
                    sn = s.sec(tgt)
                    if sn in (".rdata", ".data", ".text", ".rodata") or sn:
                        t = s.str_at(tgt)
                        if t:
                            res.append(t)
        seen, out = set(), []
        for t in res:
            if t not in seen:
                seen.add(t); out.append(t)
        return out

    def str_at(s, rva):
        raw = s.bytes_at(rva, 260)
        if len(raw) < 8:
            return None
        if raw[1] == 0 and raw[0] < 32 or raw[0] < 32 or raw[0] >= 127:
            # not text: maybe a pointer slot (e.g. static literal table) holding an absolute pointer to a string
            q = struct.unpack_from("<Q", raw, 0)[0]
            r2 = q - s.image_base
            if 0 < r2 < s.size_of_image and r2 != rva:
                t = s.str_at(r2) if s.sec(r2) else None
                return ("->" + t) if t else None
            return None
        # UTF-16LE
        i = 0
        while i + 1 < len(raw) and raw[i + 1] == 0 and 32 <= raw[i] < 127:
            i += 2
        if i >= 8:
            return "W:" + raw[:i:2].decode("ascii")
        i = 0
        while i < len(raw) and 32 <= raw[i] < 127:
            i += 1
        if i >= 6 and (i == len(raw) or raw[i] == 0):
            return "A:" + raw[:i].decode("ascii")
        return None

    def call_before(s, rva):
        """True if bytes before rva form a call instruction (E8 rel32, FF /2 forms)."""
        b = s.bytes_at(rva - 8, 8)
        if len(b) < 8:
            return False
        if b[3] == 0xE8:
            return True
        if b[6] == 0xFF and (b[7] >> 3) & 7 == 2 and (b[7] >> 6) == 3:   # call reg
            return True
        if b[5] == 0xFF and b[6] >> 3 & 7 == 2:        # ff /2 modrm + (sib/disp8)
            return True
        if b[4] == 0xFF and b[5] >> 3 & 7 == 2:
            return True
        if b[2] == 0xFF and b[3] >> 3 & 7 == 2:
            return True
        if b[1] == 0xFF and b[2] >> 3 & 7 == 2:
            return True
        if b[0] == 0xFF and b[1] >> 3 & 7 == 2:
            return True
        return False


def dll_exports(path):
    """(rva, name) sorted, from the export table of a DLL on disk."""
    p = PE(path)
    rva, sz = p.exp
    if not rva:
        return []
    t = p.bytes_at(rva, 40)
    nfun, nnam, af, an, ao = struct.unpack_from("<IIIII", t, 20)
    fun = p.bytes_at(af, nfun * 4); nm = p.bytes_at(an, nnam * 4); od = p.bytes_at(ao, nnam * 2)
    out = []
    for i in range(nnam):
        n = struct.unpack_from("<I", nm, i * 4)[0]; o = struct.unpack_from("<H", od, i * 2)[0]
        r = struct.unpack_from("<I", fun, o * 4)[0]
        out.append((r, p.bytes_at(n, 64).split(b"\0")[0].decode("ascii", "replace")))
    out.sort()
    return out


def frames_of(st, pe, base, size):
    """Distinct consecutive exe functions (function start RVAs) of call-preceded return addresses found on the stack bytes."""
    fr = []
    for i in range(0, len(st) - 7, 8):
        v = struct.unpack_from("<Q", st, i)[0]
        if base <= v < base + size:
            rva = v - base
            if pe.sec(rva) == ".text" and pe.call_before(rva):
                f = pe.func_of(rva)
                if f is not None and (not fr or fr[-1] != f):
                    fr.append(f)
    return fr


def thread_report(a, ml, base, size, pe):
    tj = os.path.join(a.run, "stack_threads.jsonl")
    if not os.path.exists(tj):
        print("\n== other threads: no stack_threads.jsonl ==")
        return
    trows = [json.loads(l) for l in open(tj)]
    print("\n== other threads: %d samples ==" % len(trows))
    if not trows:
        return
    tb = open(os.path.join(a.run, "stack_threads.bin"), "rb")
    ex = {}
    for m in ml:
        b = os.path.basename(m["path"]).lower()
        if b in ("ntdll.dll", "kernel32.dll", "kernelbase.dll", "user32.dll", "win32u.dll", "ws2_32.dll", "mswsock.dll"):
            try:
                ex[b] = (int(m["base"], 16), m["size"], dll_exports(m["path"]))
            except Exception as e:
                print("  export parse failed %s: %s" % (b, e))

    def where(rip):
        if base <= rip < base + size:
            f = pe.func_of(rip - base)
            return "exe+0x%X" % (f if f is not None else rip - base)
        for b, (mb, ms, nm) in ex.items():
            if mb <= rip < mb + ms:
                i = bisect.bisect_right([n[0] for n in nm], rip - mb) - 1
                return "%s!%s+0x%X" % (b, nm[i][1], rip - mb - nm[i][0]) if i >= 0 else b
        for m in ml:
            b = int(m["base"], 16)
            if b <= rip < b + m["size"]:
                return "%s+0x%X" % (os.path.basename(m["path"]), rip - b)
        return "?0x%X" % rip

    def group_name(n):
        import re
        return re.sub(r"\s*#?\d+$", "", n).strip() or n
    groups = collections.defaultdict(list)
    for r in trows:
        groups[group_name(r["name"])].append(r)
    for g, rs in sorted(groups.items()):
        tids = sorted({r["tid"] for r in rs})
        print("\n-- %s: %d samples, %d thread(s) %s, max suspension %.3f ms" % (g, len(rs), len(tids), tids[:6], max(r["susp_ms"] for r in rs)))
        rip_c = collections.Counter(); fr_c = collections.Counter(); first = {}
        series = []
        for r in rs:
            rip = int(r["regs"]["rip"], 16)
            w = where(rip)
            rip_c[w.split("+0x")[0]] += 1
            tb.seek(r["stack_off"]); st = tb.read(r["stack_len"])
            fr = frames_of(st, pe, base, size)
            key = fr[0] if fr else None
            fr_c[tuple(fr[:3])] += 1
            series.append((r["t"], w.split("+0x")[0], key))
            if key is not None and key not in first:
                first[key] = []
        print("  RIP (module!function), % of samples:")
        for k, c in rip_c.most_common(5):
            print("   %5.1f%%  %s" % (100.0 * c / len(rs), k))
        print("  nearest exe frames (innermost 3 call-preceded return addresses, function RVAs), % of samples:")
        for k, c in fr_c.most_common(5):
            print("   %5.1f%%  %s" % (100.0 * c / len(rs), " <- ".join("0x%X" % x for x in k) if k else "(none)"))
        topf = [k[0] for k, c in fr_c.most_common(3) if k]
        for f in topf[:2]:
            ss = pe.strings_of(f)
            print("   strings of 0x%X: %s" % (f, "; ".join(x[:70] for x in ss[:6]) if ss else "-"))
        series.sort()
        t0 = series[0][0]
        nb = 4
        span = max(series[-1][0] - t0, 1e-9)
        print("  over time (4 equal slices of the window): top innermost exe frame / top RIP")
        for q in range(nb):
            sl = [x for x in series if t0 + span * q / nb <= x[0] <= t0 + span * (q + 1) / nb + 1e-9]
            if not sl:
                continue
            kc = collections.Counter(x[2] for x in sl).most_common(1)[0]
            rc = collections.Counter(x[1] for x in sl).most_common(1)[0]
            print("   slice %d (%d): frame %s x%d, RIP %s x%d" % (q + 1, len(sl), "0x%X" % kc[0] if kc[0] else "-", kc[1], rc[0], rc[1]))


def gamethread_this_class(a, rows, base, size, pe, cm):
    """For each sample whose stack holds 0x4605AF0 or 0x41AD070 (exe RVAs, build CL-131439), take the first vtable-like object among
    rcx, rbx, rdi, rsi, r14, r15 and histogram its ClassPrivate (+0x10). Heuristic: the register that holds `this` is not known."""
    binf = open(os.path.join(a.run, "stack_samples.bin"), "rb")
    targets = {0x4605AF0: "0x4605AF0", 0x41AD070: "0x41AD070"}
    per = collections.defaultdict(collections.Counter)
    cnt = collections.Counter()
    for r in rows:
        rip = int(r["regs"]["rip"], 16)
        inner = None
        if base <= rip < base + size:
            f = pe.func_of(rip - base)
            if f in targets:
                inner = f
        if inner is None:
            binf.seek(r["stack_off"]); st = binf.read(r["stack_len"])
            for f in frames_of(st, pe, base, size):
                if f in targets:
                    inner = f; break
        if inner is None:
            continue
        cnt[inner] += 1
        found = None
        for reg in ("rcx", "rbx", "rdi", "rsi", "r14", "r15"):
            hx = r.get("objs", {}).get(r["regs"][reg])
            if not hx:
                continue
            q = struct.unpack("<4Q", bytes.fromhex(hx))
            if base <= q[0] < base + size and pe.sec(q[0] - base) == ".rdata":
                found = (reg, q[2]); break
        if found is None:   # fallback: first object seen anywhere (regs / first 64 stack qwords) whose ClassPrivate is in classmap
            for ad, hx in r.get("objs", {}).items():
                q = struct.unpack("<4Q", bytes.fromhex(hx))
                if q[2] in cm and base <= q[0] < base + size:
                    found = ("stack", q[2]); break
        per[inner][found[1] if found else None] += 1
    print("\n== GameThread: `this` class per caller (innermost of 0x4605AF0 / 0x41AD070 on the stack) ==")
    for f, c in cnt.most_common():
        print(" caller %s: %d samples" % (targets[f], c))
        for k, n in per[f].most_common(8):
            print("   %4d  %s" % (n, ("class 0x%X %s" % (k, cm.get(k, "?"))) if k else "(no vtable-like object in rcx/rbx/rdi/rsi/r14/r15)"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--exe")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--classmap")
    a = ap.parse_args()
    if not os.path.exists(os.path.join(a.run, "stack_modules.json")):
        print("no stack_modules.json (sampler never wrote it: the run never reached the world load); nothing to analyse")
        return 0
    mods = json.load(open(os.path.join(a.run, "stack_modules.json")))
    mods["start"] = mods.get("start") or []
    mods["end"] = mods.get("end") or []
    ml = mods["start"] or mods["end"]
    if not ml:
        print("no module list in stack_modules.json (0 samples: the run never reached the world load); nothing to analyse")
        return 0
    exe = None
    for m in ml:
        if m["path"].lower().endswith("shipping.exe") or (a.exe and os.path.basename(m["path"]).lower() == os.path.basename(a.exe).lower()):
            exe = m; break
    if exe is None:
        exe = ml[0]
    base, size = int(exe["base"], 16), exe["size"]
    pe = PE(a.exe or exe["path"])
    sj = os.path.join(a.run, "stack_samples.jsonl")
    rows = [json.loads(l) for l in open(sj)] if os.path.exists(sj) else []
    binf = open(os.path.join(a.run, "stack_samples.bin"), "rb")
    N = len(rows)
    print("samples %d, exe base 0x%X size 0x%X, pdata functions %d, max suspension %.3f ms" % (N, base, size, len(pe.funcs), max([r["susp_ms"] for r in rows] or [0])))
    if not N:
        return 1
    other = collections.Counter()
    rip_h = collections.Counter()
    ret_h = collections.Counter()
    for r in rows:
        rip = int(r["regs"]["rip"], 16)
        if base <= rip < base + size:
            f = pe.func_of(rip - base)
            rip_h[f if f is not None else -1] += 1
        else:
            nm = "?"
            for m in mods["start"] + mods["end"]:
                b = int(m["base"], 16)
                if b <= rip < b + m["size"]:
                    nm = os.path.basename(m["path"]); break
            other[nm] += 1
        binf.seek(r["stack_off"]); st = binf.read(r["stack_len"])
        seen = set()
        for i in range(0, len(st) - 7, 8):
            v = struct.unpack_from("<Q", st, i)[0]
            if base <= v < base + size:
                rva = v - base
                if pe.sec(rva) == ".text" and pe.call_before(rva):
                    f = pe.func_of(rva)
                    if f is not None:
                        seen.add(f)
        rf = pe.func_of(int(r["regs"]["rip"], 16) - base) if base <= int(r["regs"]["rip"], 16) < base + size else None
        if rf is not None:
            seen.add(rf)
        for f in seen:
            ret_h[f] += 1
    print("RIP outside the exe:", dict(other))
    print("\n== RIP in function (top %d), RVA of function start ==" % a.top)
    for f, c in rip_h.most_common(a.top):
        print("  %5.1f%%  0x%X" % (100.0 * c / N, f if f != -1 else 0))
    print("\n== function on the call chain (return address or RIP), %% of samples ==")
    chain = ret_h.most_common(a.top * 3)
    for f, c in chain[:a.top * 2]:
        print("  %5.1f%%  0x%X  size 0x%X" % (100.0 * c / N, f, sum(e - b for b, e, rt in pe.funcs if rt == f)))
    print("\n== strings referenced by the top functions (RIP-hot + stable chain) ==")
    shown = set()
    cand = [f for f, c in rip_h.most_common(8)] + [f for f, c in chain if c >= 0.5 * N][:a.top * 2]
    for f in cand:
        if f in shown or f == -1:
            continue
        shown.add(f)
        strs = pe.strings_of(f)
        print("  0x%X  rip %.0f%% chain %.0f%%" % (f, 100.0 * rip_h.get(f, 0) / N, 100.0 * ret_h.get(f, 0) / N))
        for t in strs[:8]:
            print("       " + t[:150])
    hit = []
    print("\n== sanity: function referencing 'routing FinishDestroy' ==")
    for f in sorted(ret_h, key=lambda x: -ret_h[x])[:200]:
        if any("routing FinishDestroy" in t for t in pe.strings_of(f)):
            print("  0x%X on the chain in %.0f%% of samples" % (f, 100.0 * ret_h[f] / N)); hit.append(f)
    if not hit:
        print("  none of the top 200 chain functions references it")
    # ---- immediate callee of the purge function, and non-exe RIP modules ----
    if hit:
        tgt = hit[0]
        child = collections.Counter(); ext = collections.Counter()
        for r in rows:
            rip = int(r["regs"]["rip"], 16)
            binf.seek(r["stack_off"]); st = binf.read(r["stack_len"]); fr = []
            for i in range(0, len(st) - 7, 8):
                v = struct.unpack_from("<Q", st, i)[0]
                if base <= v < base + size and pe.sec(v - base) == ".text" and pe.call_before(v - base):
                    f = pe.func_of(v - base)
                    if f is not None and (not fr or fr[-1] != f):
                        fr.append(f)
            top = pe.func_of(rip - base) if base <= rip < base + size else None
            if tgt in fr:
                k = fr.index(tgt)
                child[fr[k - 1] if k > 0 else (-2 if top == tgt else -1)] += 1
            if top is None:
                for m_ in mods["start"] + mods["end"]:
                    b = int(m_["base"], 16)
                    if b <= rip < b + m_["size"]:
                        ext[(os.path.basename(m_["path"]), rip - b)] += 1; break
        print("\n== immediate callee of 0x%X (-2 = RIP inside it, -1 = leaf unknown), %% of samples ==" % tgt)
        for k, c in child.most_common(10):
            print("  %5.1f%%  %s" % (100.0 * c / N, hex(k) if k > 0 else k))
        print("== RIP outside the exe: module+offset (resolve with the module exports) ==")
        for (mn, off), c in ext.most_common(10):
            print("  %4d  %s+0x%X" % (c, mn, off))
    # ---- tier 2 ----
    cm = {}
    cpath = a.classmap or os.path.join(a.run, "classmap.tsv")
    if os.path.exists(cpath):
        for l in open(cpath, encoding="utf-8", errors="replace"):
            p = l.rstrip("\n").split("\t")
            if len(p) >= 2:
                try:
                    cm[int(p[0], 16)] = p[1]
                except ValueError:
                    pass
    print("\n== tier 2: objects (first qword in exe .rdata = vtable); classmap entries: %d ==" % len(cm))
    cls_h = collections.Counter(); vt_h = collections.Counter(); nobj = 0; known = 0
    for r in rows:
        for addr, hx in r.get("objs", {}).items():
            q = struct.unpack("<4Q", bytes.fromhex(hx))
            if base <= q[0] < base + size and pe.sec(q[0] - base) in (".rdata",):
                nobj += 1
                vt_h[q[0] - base] += 1
                cls_h[q[2]] += 1
                if q[2] in cm:
                    known += 1
    print("  vtable-like objects seen: %d, of which +0x10 in classmap: %d" % (nobj, known))
    for v, c in vt_h.most_common(10):
        print("  vtable rva 0x%X  %d" % (v, c))
    for v, c in cls_h.most_common(15):
        print("  class 0x%X  %d  %s" % (v, c, cm.get(v, "?")))
    gamethread_this_class(a, rows, base, size, pe, cm)
    thread_report(a, ml, base, size, pe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
