#!/usr/bin/env python3
"""Per-thread CPU and wait state around the lobby -> L_SN2World purge (2026-11-24).
Usage: python -I gc_thread_window.py <run folder>   (needs Subnautica2.log + thread_samples.tsv from gc_thread_sampler.py)
Window = log line 'LogLoad: LoadMap: ...L_SN2World' to 'SkyLight change' (end of samples if the log never reaches it, e.g. a crash).
Prints: CPU % per thread (CPU-time delta / wall time) in the window and in the 10 s before it; per-second timeline of GameThread,
RenderThread, RHIThread (CPU % and dominant state); dominant state of the 3 main threads; top 5 other threads by window CPU."""
import sys, os, re, datetime, collections

WR = ["Executive", "FreePage", "PageIn", "PoolAllocation", "DelayExecution", "Suspended", "UserRequest", "WrExecutive", "WrFreePage",
      "WrPageIn", "WrPoolAllocation", "WrDelayExecution", "WrSuspended", "WrUserRequest", "WrEventPair", "WrQueue", "WrLpcReceive",
      "WrLpcReply", "WrVirtualMemory", "WrPageOut", "WrRendezvous", "WrKeyedEvent", "WrTerminated", "WrProcessInSwap",
      "WrCpuRateControl", "WrCalloutStack", "WrKernel", "WrResource", "WrPushLock", "WrMutex", "WrQuantumEnd", "WrDispatchInt"]
ST = ["init", "ready", "running", "standby", "terminated", "waiting", "transition", "deferred"]
MAIN = ["GameThread", "RenderThread", "RHIThread"]


def state_label(st, wr):
    if st == 5:
        return "wait:" + (WR[wr] if wr < len(WR) else str(wr))
    return ST[st] if st < len(ST) else str(st)


def log_epoch(l):
    m = re.match(r"\[(\d{4})\.(\d\d)\.(\d\d)-(\d\d)\.(\d\d)\.(\d\d):(\d{3})\]", l)
    if not m:
        return None
    y, mo, d, h, mi, s, ms = map(int, m.groups())
    return datetime.datetime(y, mo, d, h, mi, s, ms * 1000, datetime.timezone.utc).timestamp()


def main():
    run = sys.argv[1]
    lines = open(os.path.join(run, "Subnautica2.log"), encoding="utf-8", errors="replace").read().splitlines()
    t0 = t1 = None
    for l in lines:
        if t0 is None and "LogLoad: LoadMap:" in l and "L_SN2World" in l:
            t0 = log_epoch(l)
        elif t0 is not None and "SkyLight change" in l:
            t1 = log_epoch(l); break
    if t0 is None:
        print("no L_SN2World LoadMap line"); return
    S = collections.defaultdict(list)   # tid -> [(epoch, cpu_100ns, state, wr, cycles)]
    names = collections.defaultdict(collections.Counter)
    last_ep = 0
    for i, l in enumerate(open(os.path.join(run, "thread_samples.tsv"), encoding="utf-8")):
        if i == 0:
            continue
        p = l.rstrip("\n").split("\t")
        if len(p) < 10:
            continue
        ep = float(p[1]); tid = int(p[2]); last_ep = max(last_ep, ep)
        S[tid].append((ep, int(p[4]) + int(p[5]), int(p[7]), int(p[8]), int(p[6])))
        if p[3]:
            names[tid][p[3]] += 1
    if t1 is None:
        t1 = last_ep
    name = {t: (names[t].most_common(1)[0][0] if names[t] else "tid%d" % t) for t in S}
    print("run %s" % os.path.basename(os.path.normpath(run)))
    print("window %.3f s (LoadMap -> %s)  sample coverage %.3f..%.3f" % (
        t1 - t0, "SkyLight" if t1 != last_ep else "end of samples", min(r[0][0] for r in S.values()) - t0, last_ep - t0))
    print("thread names seen: " + ", ".join(sorted(set(name.values())))[:600])

    def cpu(tid, a, b):
        r = [x for x in S[tid] if a <= x[0] <= b]
        if len(r) < 2:
            return None
        return 100.0 * (r[-1][1] - r[0][1]) / 1e7 / (r[-1][0] - r[0][0])

    def dom(tid, a, b):
        r = [x for x in S[tid] if a <= x[0] <= b]
        if not r:
            return "-"
        c = collections.Counter(state_label(x[2], x[3]) for x in r)
        return ", ".join("%s %d%%" % (k, 100 * v // len(r)) for k, v in c.most_common(2))

    pre_a, pre_b = t0 - 10, t0
    rows = []
    for t in S:
        w, p = cpu(t, t0, t1), cpu(t, pre_a, pre_b)
        rows.append((t, name[t], p, w))
    print("\n== CPU %% per thread (100 = one core): pre = 10 s before LoadMap, win = purge window (%.1f s)" % (t1 - t0))
    print("%-8s %-28s %8s %8s" % ("tid", "name", "pre %", "win %"))
    for t, n, p, w in sorted(rows, key=lambda r: -((r[3] or 0) + (r[2] or 0))):
        if (p or 0) >= 0.5 or (w or 0) >= 0.5:
            print("%-8d %-28s %8s %8s" % (t, n[:28], "-" if p is None else "%.1f" % p, "-" if w is None else "%.1f" % w))
    mains = {}
    for m in MAIN:
        c = [t for t in S if name[t].startswith(m)]
        mains[m] = max(c, key=lambda t: len(S[t])) if c else None
    others = sorted((r for r in rows if r[0] not in mains.values()), key=lambda r: -(r[3] or 0))[:5]
    print("\n== top 5 other threads by window CPU")
    for t, n, p, w in others:
        print("%-8d %-28s pre %s  win %s  state in window: %s" % (t, n[:28], "-" if p is None else "%.1f" % p, "-" if w is None else "%.1f" % w, dom(t, t0, t1)))
    print("\n== dominant state in the purge window")
    for m, t in mains.items():
        print("%-13s %s" % (m, "tid %d: %s (pre-window: %s)" % (t, dom(t, t0, t1), dom(t, pre_a, pre_b)) if t else "NOT FOUND"))
    print("\n== per-second timeline (sec relative to LoadMap; CPU % / dominant state)")
    ids = [m for m in MAIN]
    print("%6s " % "sec" + " | ".join("%-34s" % m for m in ids))
    a = int(-3)
    while t0 + a <= t1 + 2:
        cells = []
        for m in ids:
            t = mains[m]
            if t is None:
                cells.append("%-34s" % "-"); continue
            c = cpu(t, t0 + a, t0 + a + 1)
            cells.append("%-34s" % ("%s%% %s" % ("-" if c is None else "%.0f" % c, dom(t, t0 + a, t0 + a + 1).split(",")[0])))
        mark = " <" if a == 0 else ""
        print("%6d " % a + " | ".join(cells) + mark)
        a += 1


main()
