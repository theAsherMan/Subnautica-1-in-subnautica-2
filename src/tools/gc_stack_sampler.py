#!/usr/bin/env python3
"""GameThread stack sampler for the lobby -> L_SN2World GC purge (2026-11-24). Run WITHOUT -I (uses psutil via gc_thread_sampler).
Usage: python gc_stack_sampler.py <run dir> [--log <Subnautica2.log>] [--exe NAME] [--hz 20] [--max-sample-seconds 25]
                                   [--max-seconds 200] [--tid N] [--now]
Waits for the game process, follows the live game log (only lines newer than the process start) and, on the
'LogLoad: LoadMap: ... L_SN2World' line, samples the thread named GameThread at --hz for up to --max-sample-seconds,
or until a 'SkyLight change' line appears, or the process exits. Per sample:
  OpenThread(SUSPEND_RESUME|GET_CONTEXT|QUERY_INFORMATION) -> SuspendThread -> GetThreadContext (CONTEXT_FULL, 16-byte aligned)
  -> ReadProcessMemory(64 KB from RSP) -> ResumeThread (in finally; resumes until the suspend count is 0).
Everything else (pointer reads for tier 2) happens AFTER the thread is resumed.
Output in <run dir>: stack_samples.jsonl (one JSON line per sample: t epoch, susp_ms, regs hex, stack offset/len into
stack_samples.bin, objs {addr: 32 bytes hex} read after resume for pointer-like registers and the first 64 stack qwords),
stack_samples.bin (raw 64 KB stacks), stack_modules.json (module bases/sizes, taken at start and at the end), stack_sampler.log.
Test options: --tid N samples that thread directly, --now skips the log trigger (used on a harmless python process)."""
import argparse, ctypes, ctypes.wintypes as wt, datetime, gc, json, os, re, sys, time
import psutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gc_thread_sampler import Sampler  # snapshot(), name()

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
k32.OpenThread.restype = wt.HANDLE
k32.OpenThread.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.SuspendThread.restype = wt.DWORD
k32.SuspendThread.argtypes = [wt.HANDLE]
k32.ResumeThread.restype = wt.DWORD
k32.ResumeThread.argtypes = [wt.HANDLE]
k32.GetThreadContext.argtypes = [wt.HANDLE, ctypes.c_void_p]
k32.GetThreadContext.restype = wt.BOOL
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = wt.BOOL
k32.CloseHandle.argtypes = [wt.HANDLE]
psapi.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD]
psapi.GetModuleFileNameExW.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_wchar_p, wt.DWORD]
psapi.GetModuleInformation.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wt.DWORD]

THREAD_ACCESS = 0x0002 | 0x0008 | 0x0040 | 0x0800   # SUSPEND_RESUME | GET_CONTEXT | QUERY_INFORMATION | QUERY_LIMITED_INFORMATION
PROC_ACCESS = 0x0400 | 0x0010                       # QUERY_INFORMATION | VM_READ
CONTEXT_FULL = 0x10000B                             # AMD64: CONTROL | INTEGER | FLOATING_POINT
CTX_SIZE = 1232
# CONTEXT offsets (x64): ContextFlags 48, Rax 120, Rcx 128, Rdx 136, Rbx 144, Rsp 152, Rbp 160, Rsi 168, Rdi 176, R8..R15 184.., Rip 248
REG_OFF = [("rax", 120), ("rcx", 128), ("rdx", 136), ("rbx", 144), ("rsp", 152), ("rbp", 160), ("rsi", 168), ("rdi", 176),
           ("r8", 184), ("r9", 192), ("r10", 200), ("r11", 208), ("r12", 216), ("r13", 224), ("r14", 232), ("r15", 240), ("rip", 248)]
STACK_BYTES = 64 * 1024
PAGE = 4096


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p), ("AllocationProtect", wt.DWORD),
                ("PartitionId", wt.WORD), ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t


def region_info(hproc, addr):
    """(base, size, state, protect, alloc_base) of the memory region holding addr, or None. Diagnostic only."""
    m = MBI()
    if not k32.VirtualQueryEx(hproc, ctypes.c_void_p(addr), ctypes.byref(m), ctypes.sizeof(m)):
        return None
    return (m.BaseAddress or 0, m.RegionSize, m.State, m.Protect, m.AllocationBase or 0)


def read_stack(hproc, rsp, buf, cap):
    """Copy up to cap bytes from rsp into buf. One big read first; if that fails (a range crossing an unreadable
    page fails as a whole: that capped earlier runs at 1-4 KB), copy page by page until the first unreadable page.
    Returns the byte count (0 = nothing readable)."""
    got = ctypes.c_size_t(0)
    if k32.ReadProcessMemory(hproc, ctypes.c_void_p(rsp), buf, cap, ctypes.byref(got)):
        return cap
    total = 0
    base = ctypes.addressof(buf)
    while total < cap:
        chunk = min(cap - total, PAGE - ((rsp + total) % PAGE))
        got.value = 0
        if not k32.ReadProcessMemory(hproc, ctypes.c_void_p(rsp + total), ctypes.c_void_p(base + total), chunk, ctypes.byref(got)):
            total += got.value
            break
        total += chunk
    return total


class Ctx:
    def __init__(self):
        self.raw = ctypes.create_string_buffer(CTX_SIZE + 32)
        a = ctypes.addressof(self.raw)
        self.off = (-a) % 16
        self.addr = a + self.off
        self.rbuf = ctypes.create_string_buffer(STACK_BYTES)
        self.obuf = ctypes.create_string_buffer(32)

    def reset(self):
        ctypes.memset(self.addr, 0, CTX_SIZE)
        ctypes.c_ulong.from_address(self.addr + 48).value = CONTEXT_FULL

    def reg(self, off):
        return ctypes.c_ulonglong.from_address(self.addr + off).value


def modules(hproc):
    arr = (ctypes.c_void_p * 2048)()
    need = wt.DWORD(0)
    if not psapi.EnumProcessModulesEx(hproc, arr, ctypes.sizeof(arr), ctypes.byref(need), 3):
        return []
    out = []
    for i in range(min(need.value // 8, 2048)):
        name = ctypes.create_unicode_buffer(520)
        psapi.GetModuleFileNameExW(hproc, arr[i], name, 520)
        mi = (ctypes.c_ulonglong * 3)()   # MODULEINFO: base, size(u32 padded), entry
        psapi.GetModuleInformation(hproc, arr[i], mi, 24)
        out.append({"base": "0x%X" % (arr[i] or 0), "size": int(mi[1]) & 0xFFFFFFFF, "path": name.value})
    return out


def log_epoch(l):
    m = re.match(r"\[(\d{4})\.(\d\d)\.(\d\d)-(\d\d)\.(\d\d)\.(\d\d):(\d{3})\]", l)
    if not m:
        return None
    y, mo, d, h, mi, s, ms = map(int, m.groups())
    return datetime.datetime(y, mo, d, h, mi, s, ms * 1000, datetime.timezone.utc).timestamp()


class LogTail:
    def __init__(self, path, since):
        self.path, self.since, self.pos = path, since, 0

    def new_lines(self):
        try:
            sz = os.path.getsize(self.path)
        except OSError:
            return []
        if sz < self.pos:
            self.pos = 0
        if sz == self.pos:
            return []
        with open(self.path, "rb") as f:
            f.seek(self.pos)
            data = f.read()
        nl = data.rfind(b"\n")
        if nl < 0:
            return []
        self.pos += nl + 1
        out = []
        for l in data[:nl].decode("utf-8", "replace").splitlines():
            e = log_epoch(l)
            if e is not None and e >= self.since - 1:
                out.append(l)
        return out


def find_proc(exe, wait):
    end = time.time() + wait
    while True:
        for p in psutil.process_iter(["name"]):
            if (p.info["name"] or "").lower() == exe.lower():
                return p
        if time.time() > end:
            return None
        time.sleep(0.3)


OTHER_RE = re.compile(r"RenderThread|RHIThread|RHISubmission|RHIInterrupt|IoDispatcher|AsyncLoad|FileIO|IOThread|LoadingThread|Worker|TaskGraph|ThreadPool", re.I)
OTHER_STACK = 16 * 1024
DEEP_RE = re.compile(r"^(RenderThread|RHIThread|RHISubmission|RHIInterrupt)", re.I)   # these get the full STACK_BYTES


def grab_other(hproc, hthread, ctx, cap=OTHER_STACK):
    """Suspend one non-GameThread thread, copy context + up to cap bytes from RSP (page-wise), resume (finally). Returns (regs, stack, susp_ms) or None."""
    ctx.reset()
    n = 0
    ok = False
    t0 = time.perf_counter()
    prev = k32.SuspendThread(hthread)
    try:
        if prev != 0xFFFFFFFF and k32.GetThreadContext(hthread, ctypes.c_void_p(ctx.addr)):
            n = read_stack(hproc, ctx.reg(152), ctx.rbuf, cap)
            ok = n > 0
    finally:
        if prev != 0xFFFFFFFF:
            while True:
                c = k32.ResumeThread(hthread)
                if c in (0, 1, 0xFFFFFFFF):
                    break
    susp = (time.perf_counter() - t0) * 1000.0
    if not ok:
        return None
    return {nm: ctx.reg(off) for nm, off in REG_OFF}, bytes(ctx.rbuf.raw[:n]), susp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--log")
    ap.add_argument("--exe", default="Subnautica2-Win64-Shipping.exe")
    ap.add_argument("--pid", type=int)
    ap.add_argument("--tid", type=int)
    ap.add_argument("--now", action="store_true")
    ap.add_argument("--hz", type=float, default=20)
    ap.add_argument("--max-sample-seconds", type=float, default=25)
    ap.add_argument("--max-seconds", type=float, default=200)
    ap.add_argument("--wait-start", type=float, default=60)
    ap.add_argument("--other-hz", type=float, default=5, help="sweep rate for the non-GameThread threads (0 = off)")
    a = ap.parse_args()
    os.makedirs(a.run, exist_ok=True)
    lg = open(os.path.join(a.run, "stack_sampler.log"), "w", encoding="utf-8")

    def say(m):
        lg.write("%s %s\n" % (datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3], m)); lg.flush()

    t_start = time.time()
    proc = psutil.Process(a.pid) if a.pid else find_proc(a.exe, a.wait_start)
    if proc is None:
        say("process not found"); return 3
    pid = proc.pid
    say("pid %d create_time %.3f" % (pid, proc.create_time()))
    hproc = k32.OpenProcess(PROC_ACCESS, False, pid)
    if not hproc:
        say("OpenProcess failed %d" % ctypes.get_last_error()); return 4
    mods = modules(hproc)
    # ---- fence-bundler globals (build CL-131439 RVAs, research/crashes/gc_watchdog_renderpipe_2026-11-25.md, "Fence bundler state") ----
    # depth  = int32 RecursionDepth (inc in StartRenderCommandFenceBundler @0x32C7C40, dec in Stop @0x32CB6D0)
    # evset  = byte TOptional<FTaskEvent> IsSet flag (checked by Flush/BeginFence); evptr = the qword before it
    glob_base = None
    pipe_ok = False
    exe_mod = next((m for m in mods if m["path"].lower().endswith(a.exe.lower())), None)
    if exe_mod:
        b = int(exe_mod["base"], 16)
        code = ctypes.create_string_buffer(6); got0 = ctypes.c_size_t(0)
        # `mov eax,[rip+disp]` at 0x32C7C6D: 8B 05 disp32, next insn 0x32C7C73 -> must resolve to 0xC890490
        if k32.ReadProcessMemory(hproc, ctypes.c_void_p(b + 0x32C7C6D), code, 6, ctypes.byref(got0)) and code.raw[:2] == b"\x8B\x05" \
                and 0x32C7C73 + int.from_bytes(code.raw[2:6], "little", signed=True) == 0xC890490:
            glob_base = b
            say("bundler globals: code check OK, exe base 0x%X" % b)
        else:
            say("bundler globals: code check FAILED (other build?) - not reading them")
        # FRenderThreadCommandPipe::Instance (rva 0xCD08210): Stop+0x14E is `lea rcx,[rip+disp]` (48 8D 0D) -> Instance,
        # then `call EnqueueAndLaunch` (0x32B6980) with name "InsertFence". Layout (from EnqueueAndLaunch's bytes):
        # +0 int32 ProduceIndex, +8 / +0x18 TArray<FCommand> Queues[2] {ptr, int32 num, int32 max}, +0x28 FMutex byte;
        # FCommand = 0x50 bytes, +0 = const TCHAR* Name.
        if glob_base is not None:
            code7 = ctypes.create_string_buffer(7)
            if k32.ReadProcessMemory(hproc, ctypes.c_void_p(b + 0x32CB6D0 + 0x14E), code7, 7, ctypes.byref(got0)) \
                    and code7.raw[:3] == b"\x48\x8D\x0D" \
                    and 0x32CB6D0 + 0x14E + 7 + int.from_bytes(code7.raw[3:7], "little", signed=True) == 0xCD08210:
                pipe_ok = True
                say("render command pipe: code check OK (Instance rva 0xCD08210)")
            else:
                say("render command pipe: code check FAILED - not reading it")
    glob_out = open(os.path.join(a.run, "stack_globals.jsonl"), "w", encoding="utf-8", newline="\n")
    glob_buf = ctypes.create_string_buffer(0x40)
    pipe_buf = ctypes.create_string_buffer(0x30)
    ev_watch = [0]
    glob_last = None
    glob_last_t = 0.0

    def read_globals(tag):
        nonlocal glob_last, glob_last_t
        if glob_base is None:
            return
        g = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(hproc, ctypes.c_void_p(glob_base + 0xC890458), glob_buf, 0x40, ctypes.byref(g)) or g.value != 0x40:
            return
        r = glob_buf.raw
        v = (int.from_bytes(r[0x38:0x3C], "little", signed=True), r[0x08], int.from_bytes(r[0:8], "little"))
        rec = {"depth": v[0], "evset": v[1], "evptr": "%X" % v[2], "raw": r.hex()}
        # raw bytes of the last non-null bundled event's task object (UE::Tasks FTaskBase; fences hold refs to it)
        if v[2]:
            ev_watch[0] = v[2]
        if ev_watch[0]:
            evb = ctypes.create_string_buffer(0x60)
            if k32.ReadProcessMemory(hproc, ctypes.c_void_p(ev_watch[0]), evb, 0x60, ctypes.byref(g)) and g.value == 0x60:
                rec["evwatch"] = "%X" % ev_watch[0]
                rec["evmem"] = evb.raw.hex()
                v = v + (evb.raw,)
        if pipe_ok and k32.ReadProcessMemory(hproc, ctypes.c_void_p(glob_base + 0xCD08210), pipe_buf, 0x30, ctypes.byref(g)) \
                and g.value == 0x30:
            p = pipe_buf.raw
            q = [(int.from_bytes(p[o:o + 8], "little"), int.from_bytes(p[o + 8:o + 12], "little", signed=True),
                  int.from_bytes(p[o + 12:o + 16], "little", signed=True)) for o in (0x08, 0x18)]
            pv = (int.from_bytes(p[0:4], "little", signed=True), q[0][1], q[1][1], p[0x28])
            v = v + pv
            rec.update({"prod": pv[0], "q0": "%X/%d/%d" % q[0], "q1": "%X/%d/%d" % q[1], "mutex": pv[3]})
            if (q[0][1] > 0 or q[1][1] > 0) and v != glob_last:
                names = {}
                for qi, (ptr, num, _mx) in enumerate(q):
                    if ptr == 0 or not 0 < num < 1000000:
                        continue
                    lst = []
                    for k in list(range(min(num, 6))) + ([num - 1] if num > 6 else []):
                        nb = ctypes.create_string_buffer(8)
                        sb = ctypes.create_string_buffer(96)
                        if k32.ReadProcessMemory(hproc, ctypes.c_void_p(ptr + k * 0x50), nb, 8, ctypes.byref(g)) \
                                and k32.ReadProcessMemory(hproc, ctypes.c_void_p(int.from_bytes(nb.raw, "little")), sb, 96, ctypes.byref(g)):
                            lst.append(sb.raw.decode("utf-16-le", "replace").split("\0")[0][:48])
                        else:
                            lst.append("?")
                    names["q%d" % qi] = lst
                rec["names"] = names
        tn = time.time()
        if v != glob_last or tn - glob_last_t >= 1.0:
            rec.update({"t": tn, "tag": tag})
            glob_out.write(json.dumps(rec) + "\n")
            glob_out.flush()
            glob_last, glob_last_t = v, tn
    sm = Sampler(pid)
    tail = None if a.now else LogTail(a.log, proc.create_time())
    triggered = a.now
    t_trig = time.time() if a.now else 0.0
    tid = a.tid
    ctx = Ctx()
    n = 0
    max_susp = 0.0
    errors = 0
    sleep_to = time.time()
    out_bin = open(os.path.join(a.run, "stack_samples.bin"), "wb")
    out_idx = open(os.path.join(a.run, "stack_samples.jsonl"), "w", encoding="utf-8", newline="\n")
    hthread = None
    last_poll = 0.0
    oth_bin = open(os.path.join(a.run, "stack_threads.bin"), "wb")
    oth_idx = open(os.path.join(a.run, "stack_threads.jsonl"), "w", encoding="utf-8", newline="\n")
    oth_h = {}          # tid -> handle (or None)
    oth_name = {}       # tid -> name
    oth_reg_logged = set()  # tids whose stack region was logged once
    cpu_f = open(os.path.join(a.run, "stack_cpu.jsonl"), "w", encoding="utf-8", newline="\n")   # per sweep: every thread's CPU times
    oth_next = 0.0
    oth_list_t = 0.0
    oth_n = 0
    oth_err = 0
    oth_max_susp = 0.0
    oth_sweeps = 0
    octx = Ctx()
    gc.disable()
    try:
        while time.time() - t_start < a.max_seconds:
            if not proc.is_running():
                say("process exited"); break
            now = time.time()
            if tail and now - last_poll >= (0.05 if triggered else 0.2):
                last_poll = now
                for l in tail.new_lines():
                    if not triggered and "LogLoad: LoadMap:" in l and "L_SN2World" in l:
                        triggered = True; t_trig = now; say("trigger: " + l[:140])
                    elif triggered and "SkyLight change" in l:
                        say("end: SkyLight line"); a.max_sample_seconds = 0
            read_globals("trig" if triggered else "pre")
            if not triggered:
                time.sleep(0.05); continue
            if now - t_trig > a.max_sample_seconds:
                say("sampling window over"); break
            if tid is None:
                rows = sm.snapshot() or []
                for r in rows:
                    if sm.name(r[0], True) == "GameThread":
                        tid = r[0]; say("GameThread tid %d" % tid); break
                if tid is None:
                    time.sleep(0.05); continue
            if hthread is None:
                hthread = k32.OpenThread(THREAD_ACCESS, False, tid)
                if not hthread:
                    say("OpenThread failed %d" % ctypes.get_last_error()); return 4
            # ---- sweep of the other threads (render / RHI / IO / workers), a few Hz ----
            if a.other_hz > 0 and now >= oth_next:
                oth_next = now + 1.0 / a.other_hz
                if now - oth_list_t > 2.0:
                    oth_list_t = now
                    for r in (sm.snapshot() or []):
                        t_id = r[0]
                        if t_id == tid:
                            continue
                        nm = sm.name(t_id, t_id not in oth_name or not oth_name.get(t_id))
                        if nm and nm != oth_name.get(t_id):
                            oth_name[t_id] = nm
                            if OTHER_RE.search(nm):
                                say("other thread %d '%s'" % (t_id, nm))
                oth_sweeps += 1
                # every thread's CPU time (100 ns units) at this sweep: tid -> [user, kernel, state, wait reason, context switches]
                try:
                    cpu_f.write(json.dumps({"t": time.time(), "sweep": oth_sweeps,
                                            "th": {str(r[0]): [r[1], r[2], r[3], r[4], r[5]] for r in (sm.snapshot() or [])}}) + "\n")
                except OSError as e:
                    say("cpu snapshot failed: %s" % e)
                for t_id, nm in list(oth_name.items()):
                    if not OTHER_RE.search(nm):
                        continue
                    if t_id not in oth_h:
                        oth_h[t_id] = k32.OpenThread(THREAD_ACCESS, False, t_id) or None
                    h = oth_h[t_id]
                    if not h:
                        continue
                    g = grab_other(hproc, h, octx, STACK_BYTES if DEEP_RE.search(nm) else OTHER_STACK)
                    if g is None:
                        oth_err += 1
                        continue
                    regs_o, stack_o, susp_o = g
                    if t_id not in oth_reg_logged:
                        oth_reg_logged.add(t_id)
                        ri = region_info(hproc, regs_o["rsp"])
                        ri2 = region_info(hproc, ri[0] + ri[1]) if ri else None
                        say("stack region %s rsp=%X len=%d region=%s next=%s" % (nm, regs_o["rsp"], len(stack_o),
                            ri and "%X+%X st=%X pr=%X ab=%X" % ri, ri2 and "%X+%X st=%X pr=%X ab=%X" % ri2))
                    oth_max_susp = max(oth_max_susp, susp_o)
                    off_o = oth_bin.tell()
                    oth_bin.write(stack_o)
                    oth_idx.write(json.dumps({"tid": t_id, "name": nm, "t": time.time(), "sweep": oth_sweeps, "susp_ms": round(susp_o, 3),
                                              "regs": {k: "%X" % v for k, v in regs_o.items()}, "stack_off": off_o, "stack_len": len(stack_o)}) + "\n")
                    oth_n += 1
                oth_bin.flush(); oth_idx.flush()
            # ---- one sample (suspended section kept minimal) ----
            ctx.reset()
            got = ctypes.c_size_t(0)
            ok_ctx = ok_mem = False
            t0 = time.perf_counter()
            prev = k32.SuspendThread(hthread)
            try:
                if prev != 0xFFFFFFFF:
                    ok_ctx = bool(k32.GetThreadContext(hthread, ctypes.c_void_p(ctx.addr)))
                    if ok_ctx:
                        rsp = ctx.reg(152)
                        got.value = read_stack(hproc, rsp, ctx.rbuf, STACK_BYTES)   # page-wise up to the stack end
                        ok_mem = got.value > 0
            finally:
                if prev != 0xFFFFFFFF:
                    while True:
                        c = k32.ResumeThread(hthread)
                        if c in (0, 1, 0xFFFFFFFF):
                            break
            susp = (time.perf_counter() - t0) * 1000.0
            max_susp = max(max_susp, susp)
            if prev == 0xFFFFFFFF or not ok_ctx or not ok_mem:
                errors += 1
                if errors <= 5:
                    say("sample failed prev=%s ctx=%s mem=%s err=%d" % (prev, ok_ctx, ok_mem, ctypes.get_last_error()))
            else:
                regs = {nm: ctx.reg(off) for nm, off in REG_OFF}
                stack = bytes(ctx.rbuf.raw[:got.value])
                # tier 2 candidates (after resume): registers + first 64 stack qwords that look like user-space pointers
                cands = [v for nm, v in regs.items() if nm not in ("rsp", "rip")]
                for i in range(min(64, len(stack) // 8)):
                    cands.append(int.from_bytes(stack[i * 8:i * 8 + 8], "little"))
                objs = {}
                for v in cands:
                    if 0x10000 <= v < 0x7FFFFFFF0000 and v not in objs:
                        if k32.ReadProcessMemory(hproc, ctypes.c_void_p(v), ctx.obuf, 32, ctypes.byref(got)) and got.value == 32:
                            objs["%X" % v] = ctx.obuf.raw[:32].hex()
                off = out_bin.tell()
                out_bin.write(stack)
                out_idx.write(json.dumps({"i": n, "t": time.time(), "susp_ms": round(susp, 3), "regs": {k: "%X" % v for k, v in regs.items()},
                                          "stack_off": off, "stack_len": len(stack), "objs": objs}) + "\n")
                n += 1
                if n % 20 == 0:
                    out_bin.flush(); out_idx.flush()
            sleep_to += 1.0 / a.hz
            d = sleep_to - time.time()
            if d > 0:
                time.sleep(d)
            else:
                sleep_to = time.time()
    finally:
        gc.enable()
        out_bin.close(); out_idx.close(); oth_bin.close(); oth_idx.close(); glob_out.close(); cpu_f.close()
        with open(os.path.join(a.run, "stack_thread_names.json"), "w", encoding="utf-8") as nf:
            json.dump({str(k): v for k, v in oth_name.items()}, nf)
        say("other threads: %d samples, %d failed, %d sweeps, max suspension %.3f ms" % (oth_n, oth_err, oth_sweeps, oth_max_susp))
        try:
            mods2 = modules(hproc)
        except Exception:
            mods2 = []
        json.dump({"pid": pid, "start": mods, "end": mods2}, open(os.path.join(a.run, "stack_modules.json"), "w"), indent=1)
        say("done: %d samples, %d failed, max suspension %.3f ms" % (n, errors, max_susp))
        lg.close()
    print("stack sampler: %d samples, max suspension %.3f ms" % (n, max_susp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
