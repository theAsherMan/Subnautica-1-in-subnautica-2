#!/usr/bin/env python3
"""IoStore read-request scanner for the lobby -> L_SN2World travel (hypothesis H8, 2026-11-26). Run WITHOUT -I (uses psutil + numpy).
Usage: python gc_ioq_scan.py <run dir> [--exe NAME] [--interval 1.0] [--max-seconds 150] [--probe] [--once]
Read-only: OpenProcess(QUERY_INFORMATION|VM_READ) + VirtualQueryEx / QueryWorkingSetEx / ReadProcessMemory. No suspend, no debugger.
Only MEM_PRIVATE committed pages that are currently in the process working set are read (so it never faults in untouched
pages and never touches the memory-mapped pak/ucas files, i.e. it causes no game-disk IO).
How it finds the queue (no symbols; layouts from Engine/Source/Runtime/PakFile/Internal/IoDispatcherFileBackendTypes.h, UE 5.6):
  1. discovery (once): find UTF-16 '*.ucas' strings in private memory, then every FFileIoStoreContainerFilePartition = a struct whose
     FString FilePath (+0x18: Data, Num, Max) points at such a string and whose file exists on disk (FileSize +0x08 is not trusted);
  2. per scan: find every qword that equals a partition address; the candidate FFileIoStoreReadRequest starts 0x10 bytes before it
     (+0x10 ContainerFilePartition, +0x18 Offset, +0x20 Size, +0x28 Key{FileIndex,BlockIndex}, +0x38 RefCount, +0x3C BufferRefCount,
     +0x90 Sequence, +0x94 Priority, +0x98 CreationTime(cycles), +0xC8 QueueStatus 0 NotInQueue / 1 InQueue / 2 Started / 3 Completed).
Output in <run dir>: ioq_parts.json (partition addresses, paths), ioq_scan.jsonl (one line per scan: t, dur, n, reqs [[seq, prio,
status, part, offset, size, refcount, bufref, ncomp, created, addr]...]), ioq_scan.log. --probe prints raw dumps of the first candidates."""
import argparse, ctypes, ctypes.wintypes as wt, json, os, struct, sys, threading, time
import numpy as np
import psutil

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = wt.BOOL
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.QueryPerformanceFrequency.argtypes = [ctypes.POINTER(ctypes.c_int64)]


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p), ("AllocationProtect", wt.DWORD),
                ("PartitionId", wt.WORD), ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


class WSEX(ctypes.Structure):
    _fields_ = [("VirtualAddress", ctypes.c_void_p), ("VirtualAttributes", ctypes.c_size_t)]


k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
psapi.QueryWorkingSetEx.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD]
psapi.QueryWorkingSetEx.restype = wt.BOOL

PROC_ACCESS = 0x0400 | 0x0010
MEM_COMMIT, MEM_PRIVATE = 0x1000, 0x20000
RW_OK = (0x04, 0x08, 0x40, 0x80)          # READWRITE, WRITECOPY, EXECUTE_READWRITE, EXECUTE_WRITECOPY
PAGE = 4096
CHUNK = 64 * 1024 * 1024
OVERLAP = 0x100                           # candidate struct size margin at chunk borders
REQ_SPAN = 0xD0

LOGF = None


def log(msg):
    line = "[ioq %s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    if LOGF:
        LOGF.write(line + "\n"); LOGF.flush()


def find_pid(exe):
    for p in psutil.process_iter(["name", "pid"]):
        if p.info["name"] and p.info["name"].lower().startswith(exe.lower()):
            return p.info["pid"]
    return None


def regions(h):
    """Yield (base, size) of committed private RW regions."""
    addr = 0
    m = MBI()
    while addr < 0x7FFFFFFE0000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(m), ctypes.sizeof(m)):
            break
        base = m.BaseAddress or 0
        size = m.RegionSize
        if m.State == MEM_COMMIT and m.Type == MEM_PRIVATE and (m.Protect & 0xFF) in RW_OK and not (m.Protect & 0x100):
            yield base, size
        nxt = base + size
        if nxt <= addr:
            break
        addr = nxt


def resident_runs(h, base, size):
    """Yield (start, length) runs of pages of [base, base+size) that are in the working set (QueryWorkingSetEx), max CHUNK long."""
    npg = size // PAGE
    step = 32768
    run_start = None
    for first in range(0, npg, step):
        n = min(step, npg - first)
        arr = np.zeros((n, 2), dtype=np.uint64)
        arr[:, 0] = np.uint64(base + first * PAGE) + np.arange(n, dtype=np.uint64) * np.uint64(PAGE)
        if not psapi.QueryWorkingSetEx(h, ctypes.c_void_p(arr.ctypes.data), arr.nbytes):
            # cannot query: treat the whole range as resident (rare)
            yield base + first * PAGE, n * PAGE
            continue
        v = arr[:, 1] & np.uint64(1)
        b = np.concatenate(([0], v.astype(np.int8), [0]))
        d = np.diff(b)
        starts = np.nonzero(d == 1)[0]
        ends = np.nonzero(d == -1)[0]
        for s, e in zip(starts, ends):
            yield base + (first + int(s)) * PAGE, (int(e) - int(s)) * PAGE


def read_mem(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t(0)
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)) and got.value == 0:
        return None
    return buf.raw[:got.value]


def iter_chunks(h):
    """Yield (addr, bytes) for every resident private RW chunk, chunks overlap by OVERLAP bytes."""
    for base, size in regions(h):
        for rs, rl in resident_runs(h, base, size):
            off = 0
            while off < rl:
                n = min(CHUNK + OVERLAP, rl - off)
                data = read_mem(h, rs + off, n)
                if data:
                    yield rs + off, data
                off += CHUNK


GAME_ROOT = [None]    # directory the '../../../' of container paths is relative to (<exe dir>); set in main
_SIZES = {}


def real_size(text):
    """Size on disk of a container path like ../../../Subnautica2/Content/Paks/x.ucas (0 if it does not exist). The FileSize field in the
    partition struct was seen holding a pointer in one run, so it is not used."""
    if text not in _SIZES:
        try:
            _SIZES[text] = os.stat(os.path.normpath(os.path.join(GAME_ROOT[0], text))).st_size
        except (OSError, TypeError):
            _SIZES[text] = 0
    return _SIZES[text]


def find_strings(h):
    """{address: text} of every UTF-16 '*.ucas' string in resident private memory."""
    pat = ".ucas\0".encode("utf-16le")
    strs = {}   # string start addr -> text
    for addr, data in iter_chunks(h):
        pos = 0
        while True:
            i = data.find(pat, pos)
            if i < 0:
                break
            pos = i + 2
            # walk back to the start of the wide string (printable ASCII wide chars)
            j = i
            while j >= 2 and j > i - 1000 and data[j - 1] == 0 and 0x20 <= data[j - 2] < 0x7F:
                j -= 2
            if (i - j) // 2 >= 3:
                text = data[j:i + len(pat) - 2].decode("utf-16le", "replace")
                if text.lower().endswith(".ucas"):
                    strs[addr + j] = text
    log("discovery: %d .ucas strings (%d distinct texts)" % (len(strs), len(set(strs.values()))))
    return strs


def find_parts(h, strs):
    """{partition_addr: (path, file size)} for FFileIoStoreContainerFilePartition objects whose FilePath points at one of strs."""
    if not strs:
        return {}
    keys = np.array(sorted(strs), dtype=np.uint64)
    parts = {}
    for addr, data in iter_chunks(h):
        n = (len(data) // 8)
        arr = np.frombuffer(data, dtype="<u8", count=n)
        lo, hi = keys[0], keys[-1]
        cand = np.nonzero((arr >= lo) & (arr <= hi))[0]
        for ci in cand:
            val = int(arr[ci])
            if val not in strs:
                continue
            o = int(ci) * 8 - 0x18        # struct start so that FilePath.Data is at +0x18
            if o < 0 or o + 0x30 > len(data):
                continue
            num, mx = struct.unpack_from("<ii", data, o + 0x20)
            text = strs[val]
            fsz = real_size(text)
            if num == len(text) + 1 and mx >= num and fsz:
                parts[addr + o] = (text, fsz)
    return parts


def parse_req(data, o):
    nxt, prv, part, offset, size = struct.unpack_from("<QQQQQ", data, o)[0:5]
    k_file, k_block = struct.unpack_from("<II", data, o + 0x28)
    refc, bufref = struct.unpack_from("<II", data, o + 0x38)
    ncomp = struct.unpack_from("<i", data, o + 0x88)[0]
    seq, prio, created = struct.unpack_from("<IiQ", data, o + 0x90)
    status = struct.unpack_from("<i", data, o + 0xC8)[0]
    return nxt, prv, part, offset, size, k_file, k_block, refc, bufref, ncomp, seq, prio, created, status


PATHS = []


def path_id(path):
    if path not in PATHS:
        PATHS.append(path)
    return PATHS.index(path)


def hit_requests(addr, data, idx, keys_lo, keys_hi, parts, seen, probes=None):
    """Parse every FFileIoStoreReadRequest candidate in data (read at addr). Returns request rows."""
    out = []
    n = len(data) // 8
    arr = np.frombuffer(data, dtype="<u8", count=n)
    cand = np.nonzero((arr >= keys_lo) & (arr <= keys_hi))[0]
    for ci in cand:
        val = int(arr[ci])
        if val not in idx:
            continue
        o = int(ci) * 8 - 0x10
        if o < 0 or o + REQ_SPAN > len(data):
            continue
        a = addr + o
        if a in seen:
            continue
        seen.add(a)
        if probes is not None and len(probes) < 12:
            probes.append((a, data[o:o + REQ_SPAN]))
        try:
            (nxt, prv, part, offset, size, kf, kb, refc, bufref, ncomp, seq, prio, created, status) = parse_req(data, o)
        except struct.error:
            continue
        if not (0 < size <= 64 * 1024 * 1024 and offset < parts[part][1] and 0 <= status <= 3):
            continue
        out.append([seq, prio, status, path_id(parts[part][0]), offset, size, refc, bufref, ncomp, created, a])
    return out


def scan(h, parts, probe=False):
    """Full scan of all resident private memory. Returns (rows, seconds, probes)."""
    keys = np.array(sorted(parts), dtype=np.uint64)
    lo, hi = keys[0], keys[-1]
    idx = {a: i for i, a in enumerate(sorted(parts))}
    out, probes, seen = [], [], set()
    t0 = time.time()
    for addr, data in iter_chunks(h):
        out += hit_requests(addr, data, idx, lo, hi, parts, seen, probes if probe else None)
    return out, time.time() - t0, probes


def discover(h, ucas_sizes=None):
    return find_parts(h, find_strings(h))


class Fast:
    """Re-reads only the 64 KB blocks that held requests in an earlier scan (about 100x cheaper than a full scan)."""
    BLK = 0x10000

    def __init__(self, h, parts):
        self.h, self.parts = h, parts
        self.keys = np.array(sorted(parts), dtype=np.uint64)
        self.idx = {a: i for i, a in enumerate(sorted(parts))}
        self.blocks = set()
        self.lock = threading.Lock()

    def refresh(self):
        self.keys = np.array(sorted(self.parts), dtype=np.uint64)
        self.idx = {a: i for i, a in enumerate(sorted(self.parts))}

    def add(self, rows):
        with self.lock:
            for r in rows:
                b = r[10] // self.BLK
                for d in (-2, -1, 0, 1, 2):   # neighbours: the allocator grows block by block
                    self.blocks.add(b + d)

    def scan(self):
        with self.lock:
            blks = sorted(self.blocks)
        out, seen = [], set()
        for b in blks:
            data = read_mem(self.h, b * self.BLK, self.BLK + OVERLAP)
            if data:
                out += hit_requests(b * self.BLK, data, self.idx, self.keys[0], self.keys[-1], self.parts, seen)
        return out


def main():
    global LOGF
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--exe", default="Subnautica2-Win64-Shipping")
    ap.add_argument("--interval", type=float, default=0.5, help="fast-scan period (s)")
    ap.add_argument("--full-every", type=float, default=0.0, help="pause between full scans (s); they run back to back in a thread")
    ap.add_argument("--max-seconds", type=float, default=150)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--pid", type=int, default=0)
    ap.add_argument("--log", default="", help="live game log; if given, wait for one of the --gate strings before touching the process")
    ap.add_argument("--gate", default="in location slot 1;LogInit: Display: Starting Game.", help="';'-separated log substrings; the first one seen starts the scan. 'in location slot 1' = the first mod container (mounted ~3 s after launch, memory still small, so discovery is fast)")
    a = ap.parse_args()
    try:
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    os.makedirs(a.outdir, exist_ok=True)
    LOGF = open(os.path.join(a.outdir, "ioq_scan.log"), "a")
    t_end = time.time() + a.max_seconds
    pid = a.pid
    while not pid and time.time() < t_end:
        pid = find_pid(a.exe) or 0
        time.sleep(0.5)
    if not pid:
        log("game not found")
        return 1
    h = k32.OpenProcess(PROC_ACCESS, False, pid)
    if not h:
        log("OpenProcess failed %d" % ctypes.get_last_error())
        return 1
    log("attached pid %d" % pid)
    GAME_ROOT[0] = os.path.dirname(psutil.Process(pid).exe())
    if a.log:
        # the scan itself must not slow the boot: wait for the gate line in the new log
        try:
            ctime = psutil.Process(pid).create_time()
            seen_lobby = False
            while not seen_lobby and time.time() < t_end and psutil.pid_exists(pid):
                # the live log is rewritten at game start: only trust it once its mtime is newer than the process start
                if os.path.exists(a.log) and os.stat(a.log).st_mtime >= ctime:
                    with open(a.log, "rb") as lf:
                        txt = lf.read()
                        seen_lobby = any(g.encode() in txt for g in a.gate.split(";"))
                if not seen_lobby:
                    time.sleep(0.5)
            log("gate seen: %s" % seen_lobby)
        except (OSError, psutil.Error) as e:
            log("log wait failed: %s" % e)
    strs = {}
    parts = {}
    while not parts and time.time() < t_end:
        t0 = time.time()
        strs = find_strings(h)
        parts = find_parts(h, strs)
        log("discovery took %.1fs: %d partitions" % (time.time() - t0, len(parts)))
        for ad, (txt, fs) in sorted(parts.items()):
            log("  partition %x size %d %s" % (ad, fs, txt))
        if not parts:
            time.sleep(2)
    if not parts:
        return 2
    plist = sorted(parts)
    freq = ctypes.c_int64(0)
    k32.QueryPerformanceFrequency(ctypes.byref(freq))
    def write_parts():
        with open(os.path.join(a.outdir, "ioq_parts.json"), "w") as f:
            json.dump({"qpc_freq": freq.value, "paths": PATHS}, f)
    fast = Fast(h, parts)
    stop = threading.Event()
    fulls = []

    def full_loop():
        cyc = 0
        while not stop.is_set() and time.time() < t_end and psutil.pid_exists(pid):
            cyc += 1
            if cyc > 1:   # containers can be mounted later and the Partitions arrays reallocated: re-find them every cycle (strings every 8th)
                if cyc % 8 == 0:
                    strs.update(find_strings(h))
                newp = find_parts(h, strs)
                added = [k for k in newp if k not in parts]
                parts.update(newp)
                fast.refresh()
                if added:
                    log("partitions now %d (new: %s)" % (len(parts), ", ".join("%x" % k for k in added)))
            rows, dur, probes = scan(h, parts, a.probe)
            fast.add(rows)
            fulls.append((time.time(), dur, len(rows)))
            log("full scan %.1fs: %d requests, %d blocks tracked" % (dur, len(rows), len(fast.blocks)))
            for ad, raw in probes:
                log("probe %x: %s" % (ad, raw.hex()))
            if a.once:
                break
            stop.wait(a.full_every)

    th = threading.Thread(target=full_loop, daemon=True)
    th.start()
    life = {}      # seq -> [offset, size, prio, part, created_cycles, t_first_inq, t_first_started, t_first_done, t_last_inq]
    sf = open(os.path.join(a.outdir, "ioq_scan.jsonl"), "a")
    last_dump = time.time()
    nscan = 0
    while time.time() < t_end and psutil.pid_exists(pid) and not (a.once and not th.is_alive()):
        if not fast.blocks:
            time.sleep(0.1)
            continue
        t0 = time.time()
        rows = fast.scan()
        now = time.time()
        pc = time.perf_counter()
        hist, mb_inq, started = {}, 0.0, []
        cnt = {1: 0, 2: 0, 3: 0, 0: 0}
        seqmax = 0
        for r in rows:
            seq, prio, st = r[0], r[1], r[2]
            cnt[st] = cnt.get(st, 0) + 1
            seqmax = max(seqmax, seq)
            e = life.get(seq)
            if e is None:
                e = life[seq] = [r[4], r[5], prio, r[3], r[9], None, None, None, None]
            if st == 1:
                mb_inq += r[5]
                hist[prio] = hist.get(prio, 0) + 1
                if e[5] is None:
                    e[5] = now
                e[8] = now
            elif st == 2:
                started.append(seq)
                if e[6] is None:
                    e[6] = now
            elif st == 3 and e[7] is None:
                e[7] = now
        sf.write(json.dumps({"t": round(now, 3), "pc": round(pc, 3), "dur": round(now - t0, 3), "n": len(rows), "inq": cnt[1], "started": started,
                             "done": cnt[3], "mb_inq": round(mb_inq / 1e6, 1), "seqmax": seqmax, "prio": hist}) + "\n")
        sf.flush()
        nscan += 1
        if nscan % 10 == 1:
            log("fast scan #%d %.2fs: %d requests inq=%d started=%d done=%d inq_mb=%.0f seqmax=%d prio=%s" % (nscan, now - t0, len(rows), cnt[1], len(started), cnt[3], mb_inq / 1e6, seqmax, hist))
        if now - last_dump > 10:
            json.dump(life, open(os.path.join(a.outdir, "ioq_life.json"), "w"))
            write_parts()
            last_dump = now
        time.sleep(max(0.0, a.interval - (time.time() - t0)))
    stop.set()
    write_parts()
    json.dump(life, open(os.path.join(a.outdir, "ioq_life.json"), "w"))
    log("done: %d fast scans, %d full scans, %d requests in life table" % (nscan, len(fulls), len(life)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
