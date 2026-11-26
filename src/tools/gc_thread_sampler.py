#!/usr/bin/env python3
"""Read-only per-thread sampler for Subnautica2-Win64-Shipping.exe (2026-11-24, GC purge diagnosis).
Usage: python gc_thread_sampler.py <out.tsv> [--exe NAME] [--pid N] [--interval 0.1] [--max-seconds 150] [--wait-start 60]
Every interval, for every thread of the process: TID, name (GetThreadDescription), user and kernel time (100 ns units, from
NtQuerySystemInformation(SystemProcessInformation)), CPU cycles (QueryThreadCycleTime), thread state and WaitReason, context switches.
UTC timestamps (same clock as Subnautica2.log). No SuspendThread, no debugger, no dumps. Exits when the process is gone or after --max-seconds.
Columns: utc_iso, epoch, tid, name, user_100ns, kernel_100ns, cycles, state, wait_reason, ctx_switches
state: 0 init, 1 ready, 2 running, 3 standby, 4 terminated, 5 waiting, 6 transition, 7 deferred ready. wait_reason: Windows KWAIT_REASON number
(0 Executive, 5 WrUserRequest/UserRequest 6, 8 WrQueue? see decode table in gc_thread_window.py)."""
import argparse, ctypes, ctypes.wintypes as wt, datetime, sys, time
import psutil

ntdll = ctypes.WinDLL("ntdll")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenThread.restype = wt.HANDLE
k32.OpenThread.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.GetThreadDescription.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
k32.GetThreadDescription.restype = ctypes.c_long
k32.LocalFree.argtypes = [ctypes.c_void_p]
k32.QueryThreadCycleTime.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_ulonglong)]
THREAD_QUERY_LIMITED_INFORMATION = 0x0800
ntdll.NtQuerySystemInformation.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
ntdll.NtQuerySystemInformation.restype = ctypes.c_long

SPI_HDR = 256     # SYSTEM_PROCESS_INFORMATION size on x64 (threads follow)
SPI_PID = 80      # UniqueProcessId offset
STI = 80          # SYSTEM_THREAD_INFORMATION size on x64


class Sampler:
    def __init__(self, pid):
        self.pid = pid
        self.buf = ctypes.create_string_buffer(8 * 1024 * 1024)
        self.handles = {}   # tid -> handle or None
        self.names = {}     # tid -> name

    def snapshot(self):
        need = ctypes.c_ulong(0)
        while True:
            st = ntdll.NtQuerySystemInformation(5, self.buf, len(self.buf), ctypes.byref(need))
            if st == 0:
                break
            if st & 0xFFFFFFFF == 0xC0000004:
                self.buf = ctypes.create_string_buffer(need.value + 1024 * 1024)
                continue
            raise OSError("NtQuerySystemInformation status 0x%08X" % (st & 0xFFFFFFFF))
        raw = self.buf
        off = 0
        while True:
            nxt = ctypes.c_ulong.from_buffer(raw, off).value
            pid = ctypes.c_ulonglong.from_buffer(raw, off + SPI_PID).value
            if pid == self.pid:
                n = ctypes.c_ulong.from_buffer(raw, off + 4).value
                rows = []
                for i in range(n):
                    t = off + SPI_HDR + i * STI
                    kern = ctypes.c_longlong.from_buffer(raw, t).value
                    user = ctypes.c_longlong.from_buffer(raw, t + 8).value
                    cpid = ctypes.c_ulonglong.from_buffer(raw, t + 40).value
                    tid = ctypes.c_ulonglong.from_buffer(raw, t + 48).value
                    ctx = ctypes.c_ulong.from_buffer(raw, t + 64).value
                    state = ctypes.c_ulong.from_buffer(raw, t + 68).value
                    wr = ctypes.c_ulong.from_buffer(raw, t + 72).value
                    if cpid != self.pid:
                        raise OSError("thread layout mismatch (client pid %d != %d)" % (cpid, self.pid))
                    rows.append((tid, user, kern, state, wr, ctx))
                return rows
            if nxt == 0:
                return None
            off += nxt

    def handle(self, tid):
        if tid not in self.handles:
            h = k32.OpenThread(THREAD_QUERY_LIMITED_INFORMATION, False, tid)
            self.handles[tid] = h if h else None
        return self.handles[tid]

    def name(self, tid, refresh):
        cur = self.names.get(tid)
        if cur and not refresh:
            return cur
        h = self.handle(tid)
        if not h:
            return cur or "?"
        p = ctypes.c_wchar_p()
        if k32.GetThreadDescription(h, ctypes.byref(p)) >= 0 and p.value:
            self.names[tid] = p.value
            k32.LocalFree(p)
            return self.names[tid]
        return cur or ""

    def cycles(self, tid):
        h = self.handle(tid)
        if not h:
            return -1
        c = ctypes.c_ulonglong(0)
        return c.value if k32.QueryThreadCycleTime(h, ctypes.byref(c)) else -1

    def prune(self, alive):
        for tid in [t for t in self.handles if t not in alive]:
            h = self.handles.pop(tid)
            if h:
                k32.CloseHandle(h)


def find_pid(exe, wait):
    end = time.time() + wait
    while True:
        for p in psutil.process_iter(["name"]):
            if (p.info["name"] or "").lower() == exe.lower():
                return p.pid
        if time.time() > end:
            return None
        time.sleep(0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--exe", default="Subnautica2-Win64-Shipping.exe")
    ap.add_argument("--pid", type=int)
    ap.add_argument("--interval", type=float, default=0.1)
    ap.add_argument("--max-seconds", type=float, default=150)
    ap.add_argument("--wait-start", type=float, default=60)
    a = ap.parse_args()
    t_start = time.time()
    pid = a.pid or find_pid(a.exe, a.wait_start)
    if not pid:
        print("sampler: process not found", file=sys.stderr)
        return 3
    s = Sampler(pid)
    n = 0
    last_name_refresh = 0.0
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("utc\tepoch\ttid\tname\tuser_100ns\tkernel_100ns\tcycles\tstate\twait_reason\tctx\n")
        nxt = time.time()
        while time.time() - t_start < a.max_seconds:
            now = time.time()
            try:
                rows = s.snapshot()
            except OSError as e:
                print("sampler error: %s" % e, file=sys.stderr)
                return 4
            if rows is None:
                break
            refresh = now - last_name_refresh >= 1.0
            if refresh:
                last_name_refresh = now
            ts = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            alive = set()
            out = []
            for tid, user, kern, state, wr, ctx in rows:
                alive.add(tid)
                out.append("%s\t%.3f\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d\n" % (
                    ts, now, tid, s.name(tid, refresh and s.names.get(tid) is None), user, kern, s.cycles(tid), state, wr, ctx))
            f.write("".join(out))
            n += 1
            if n % 10 == 0:
                f.flush()
                s.prune(alive)
            nxt += a.interval
            d = nxt - time.time()
            if d > 0:
                time.sleep(d)
            else:
                nxt = time.time()
    print("sampler: %d samples, pid %d" % (n, pid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
